# Ранбук: Масштабування GPU нод

Ранбук для збільшення або зменшення потужності **GPU node pool** у GKE при зміні навантаження на тренування або inference.

## Симптоми

- Поди в стані **Pending** з причини недостатності GPU (`Insufficient nvidia.com/gpu` або аналог).
- Черги в Airflow / завдання очікують вільних GPU довше SLA.
- Висока **латентність** або відмови через нестачу реплік inference — HPA не може додати поди через відсутність нод.
- Планове зниження витрат поза піком — потреба зменшити мінімальний розмір пулу.

## Діагностика

### Kubernetes

Перевірити поди, що чекають планування:

```bash
kubectl get pods -n NAMESPACE --field-selector=status.phase=Pending
kubectl describe pod -n NAMESPACE POD_NAME
```

Подивитися ресурси нод і наявність GPU:

```bash
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-T4
kubectl describe node NODE_NAME
```

Перевірити **DaemonSet** **NVIDIA GPU Operator** (якщо використовується):

```bash
kubectl get pods -n gpu-operator-resources
```

### GKE / GCP

Через **gcloud** (замініть проєкт, кластер, зону/регіон, ім’я пулу):

```bash
gcloud container node-pools describe POOL_NAME --cluster=CLUSTER_NAME --region=REGION
gcloud container clusters describe CLUSTER_NAME --region=REGION
```

У консолі GCP: **Kubernetes Engine → Clusters → Node pools** — поточні min/max/maxSurge, machine type, accelerators.

### Prometheus / Grafana

- Використання GPU по нодах і подах.
- Кількість **Pending** подів з часом.
- Кореляція з вартістю (якщо є дашборди або звіти).

## Рішення

### Збільшення ємності (більше GPU нод)

1. **Оцінити потребу:** скільки додаткових GPU потрібно (одиничні поди vs багато малих).
2. **Terraform:** змінити параметри node pool у модулі GKE (наприклад, `min_node_count`, `max_node_count`, `initial_node_count` або еквівалентні змінні вашого репозиторію).
3. Застосувати зміни:

```bash
terraform plan
terraform apply
```

4. Дочекатися створення нод; перевірити:

```bash
kubectl get nodes -l cloud.google.com/gke-accelerator
kubectl get pods -n NAMESPACE
```

5. Якщо використовується **cluster autoscaler**, переконатися, що **max** пулу дозволяє потрібний масштаб; інколи достатньо підвищити лише **max**, без зміни **min**.

### Зменшення ємності (економія)

1. Переконатися, що на пулі немає критичних подів (перенести inference на інший пул або зменшити репліки після згоди з власником сервісу).
2. У **Terraform** знизити **max** і за потреби **min** (різке зниження **min** може витіснити поди — планувати в вікно обслуговування).
3. `terraform apply`; спостерігати за **draining** нод і переплануванням подів.

### Окремий пул під inference або training

Якщо один пул перевантажений змішаним навантаженням:

1. Створити другий **node pool** з іншими taints (наприклад, `workload=inference:NoSchedule`).
2. Додати відповідні **tolerations** у deployment **llm-serving** / training **Jobs**.
3. Налаштувати **Terraform** для обох пулів і застосувати.

### Тимчасове масштабування без повного Terraform-циклу

У деяких організаціях дозволено зміну **max** через **gcloud** з наступною фіксацією в Git (щоб уникнути drift):

```bash
gcloud container clusters resize CLUSTER_NAME --node-pool POOL_NAME --num-nodes N --region=REGION
```

Після інциденту обов’язково відобразити цільовий стан у **Terraform**.

## Превенція

- **HPA** / **cluster autoscaler** узгоджені: достатній **max** node pool, щоб autoscaler міг додати ноди.
- Регулярний review **resource requests** для GPU-подів — занижені requests призводять до overcommit і конкуренції.
- Алерти на **Pending** поди з GPU та на використання пулу понад поріг.
- Документувати **min/max** у runbook інфраструктури; зміни лише через **MR** до Terraform (або узгоджений процес з anti-drift).
- Для **spot** GPU-пулів закладати запас ємності або fallback на on-demand для критичного inference.
