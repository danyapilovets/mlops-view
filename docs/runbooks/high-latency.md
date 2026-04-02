# Ранбук: Висока латентність інференсу

Ранбук для діагностики та усунення підвищеної **латентності** відповідей сервісів ML/LLM inference у Kubernetes.

## Симптоми

- Зростання **p95/p99 латентності** на шлюзі або в метриках застосунку порівняно з базовою лінією.
- Скарги користувачів на «повільні» відповіді, таймаути на клієнті.
- Черги запитів, зростання часу очікування в черзі (якщо експортується).
- Одночасне зростання використання **GPU** або **CPU** без пропорційного зростання RPS (ознака внутрішнього вузького місця).
- Алерти з **Prometheus** / **Alertmanager** за правилами латентності або saturation.

## Діагностика

### Kubernetes

Перевірити стан подів і подій у неймспейсі сервісу (замініть `NAMESPACE`, `LABEL_SELECTOR`):

```bash
kubectl get pods -n NAMESPACE -l LABEL_SELECTOR -o wide
kubectl describe pod -n NAMESPACE POD_NAME
kubectl top pods -n NAMESPACE
```

Перевірити **HPA** та поточну кількість реплік:

```bash
kubectl get hpa -n NAMESPACE
kubectl describe hpa -n NAMESPACE HPA_NAME
```

Переглянути **ресурси** та **лиміти** deployment:

```bash
kubectl get deployment -n NAMESPACE -o yaml
```

### Мережа та DNS

```bash
kubectl get svc,endpoints -n NAMESPACE
# Перевірка затримки між подами (за потреби через тимчасовий debug-pod)
```

### Prometheus / Grafana

У **Grafana** (дашборди kube-prometheus-stack / кастомні для llm-serving):

- Латентність по ендпоінтах (histogram: `*_bucket` / відповідні recording rules).
- **GPU** utilization, пам’ять GPU, черги **vLLM** (якщо експортуються).
- CPU throttling, memory pressure, кількість рестартів подів.
- Чи корелює пік латентності з **cold start** після scale-up або з **spot preemption**.

Приклад запитів у **Prometheus** (імена метрик уточнюйте під ваші recording rules):

```promql
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))
```

## Рішення

Виконуйте кроки послідовно; після кожного кроку перевіряйте метрики.

1. **Навантаження та репліки**  
   Якщо RPS зріс — збільшити `replicas` у deployment або налаштувати **HPA** (CPU/GPU/кастомна метрика черги). Переконатися, що є вільні ноди в пулі.

2. **Ресурси пода**  
   Якщо видно throttling CPU або OOM — підвищити **requests/limits** (з урахуванням квот namespace) або оптимізувати batch size для **vLLM**.

3. **GPU**  
   Переконатися, що под запланований на ноду з GPU (`kubectl describe node`), немає конкуренції за одну карту між подами без isolation. За потреби — окремий node pool або taints/tolerations.

4. **Модель і конфігурація inference**  
   Перевірити зміни в образі, розмірі моделі, **max_tokens**, **tensor parallel**, **KV cache**; відкотити останній реліз через Git / **Flux** якщо деградація збіглася з деплоєм.

5. **Мережа та шлюз**  
   Перевірити **ml-gateway**, Ingress, service mesh: таймаути, кількість з’єднань, keep-alive. Порівняти латентність «под → под» і «зовні → ingress».

6. **Залежності**  
   Якщо inference викликає зовнішні API або сховище — перевірити їхню латентність і ліміти.

7. **Тимчасове зняття навантаження**  
   За критичного інциденту: тимчасово зменшити трафік (canary, ваги в gateway), масштабувати горизонтально або переключити на резервну версію моделі з реєстру.

## Превенція

- Визначити **SLO** з латентності та алерти з розумними порогами й `for:` затримкою.
- Регресійні тести продуктивності перед промоушном моделі в production.
- **Resource requests** відповідні реальному профілю; регулярний review дашбордів **Grafana** і вартості GPU.
- Документувати зміни inference-параметрів у MR до Git; деплой лише через **Flux**.
- Для LLM — моніторинг довжини контексту та розподілу токенів; попередження про «важкі» клієнтські патерни.
