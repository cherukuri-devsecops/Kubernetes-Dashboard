{{- define "kubernetes-dashboard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "kubernetes-dashboard.namespace" -}}
{{- .Release.Namespace -}}
{{- end -}}

{{- define "kubernetes-dashboard.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "kubernetes-dashboard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: kubernetes-dashboard
{{- end -}}

{{- define "kubernetes-dashboard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubernetes-dashboard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "kubernetes-dashboard.secretName" -}}
{{- default (printf "%s-secrets" (include "kubernetes-dashboard.fullname" .)) .Values.secrets.name -}}
{{- end -}}

{{- define "kubernetes-dashboard.backendName" -}}
{{- printf "%s-backend" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.frontendName" -}}
{{- printf "%s-frontend" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.postgresName" -}}
{{- printf "%s-postgres" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.redisName" -}}
{{- printf "%s-redis" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.prometheusName" -}}
{{- printf "%s-prometheus" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.kubeStateMetricsName" -}}
{{- printf "%s-kube-state-metrics" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.nodeExporterName" -}}
{{- printf "%s-node-exporter" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.lokiName" -}}
{{- printf "%s-loki" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.fluentBitName" -}}
{{- printf "%s-fluent-bit" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.tempoName" -}}
{{- printf "%s-tempo" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.otelCollectorName" -}}
{{- printf "%s-otel-collector" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kubernetes-dashboard.metricsServerName" -}}
{{- printf "%s-metrics-server" (include "kubernetes-dashboard.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
OTLP endpoint the backend exports spans to: the collector when it is deployed,
otherwise Tempo's own receiver.
*/}}
{{- define "kubernetes-dashboard.otlpEndpoint" -}}
{{- if .Values.otelCollector.enabled -}}
http://{{ include "kubernetes-dashboard.otelCollectorName" . }}:4317
{{- else -}}
http://{{ include "kubernetes-dashboard.tempoName" . }}:4317
{{- end -}}
{{- end -}}
