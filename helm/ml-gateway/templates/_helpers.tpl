{{- define "ml-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ml-gateway.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "ml-gateway.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ml-gateway.labels" -}}
helm.sh/chart: {{ include "ml-gateway.chart" . }}
{{ include "ml-gateway.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "ml-gateway.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ml-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "ml-gateway.backendHostPort" -}}
{{- $u := .url | trimPrefix "http://" | trimPrefix "https://" -}}
{{- $u -}}
{{- end }}

{{- define "ml-gateway.nginxRate" -}}
{{- .Values.rateLimiting.rate | replace "/min" "r/m" | replace "/s" "r/s" | replace "/h" "r/h" -}}
{{- end }}
