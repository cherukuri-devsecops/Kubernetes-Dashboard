{{/*
Expand the name of the chart.
*/}}
{{- define "kube-dashboard.name" -}}
{{- default .Chart.Name .Values.global.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "kube-dashboard.fullname" -}}
{{- if .Values.global.fullnameOverride }}
{{- .Values.global.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.global.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label.
*/}}
{{- define "kube-dashboard.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "kube-dashboard.labels" -}}
helm.sh/chart: {{ include "kube-dashboard.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Selector labels for a given component.
Usage: include "kube-dashboard.selectorLabels" (dict "root" . "component" "ui-service")
*/}}
{{- define "kube-dashboard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kube-dashboard.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
ServiceAccount name for the backend.
*/}}
{{- define "kube-dashboard.backendServiceAccountName" -}}
{{- printf "%s-backend" (include "kube-dashboard.fullname" .) }}
{{- end }}

{{/*
ServiceAccount name for the bundled ingress controller.
*/}}
{{- define "kube-dashboard.ingressControllerServiceAccountName" -}}
{{- printf "%s-ingress-controller" (include "kube-dashboard.fullname" .) }}
{{- end }}

{{/*
Base selector labels (name + instance only, no component).
Used by the combined single-pod deployment and all Services so every Service
routes to the one pod regardless of which container it targets.
*/}}
{{- define "kube-dashboard.baseSelector" -}}
app.kubernetes.io/name: {{ include "kube-dashboard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
IngressClass name used by the bundled controller and the Ingress resource.
When bundledController is enabled this is derived from the release name so it
is guaranteed to be unique per install. Otherwise falls back to ingress.className.
*/}}
{{- define "kube-dashboard.ingressClassName" -}}
{{- if .Values.ingress.bundledController.enabled }}
{{- include "kube-dashboard.fullname" . }}
{{- else }}
{{- .Values.ingress.className }}
{{- end }}
{{- end }}
