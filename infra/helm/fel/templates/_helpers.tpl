{{- define "fel.fullname" -}}
{{- .Release.Name | trunc 45 | trimSuffix "-" -}}
{{- end -}}

{{- define "fel.testAnnotations" -}}
{{- if eq .root.Values.tests.hookMode "argocd" -}}
argocd.argoproj.io/hook: PostSync
argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
argocd.argoproj.io/sync-wave: {{ .wave | quote }}
{{- else -}}
helm.sh/hook: test
helm.sh/hook-delete-policy: before-hook-creation
helm.sh/hook-weight: {{ .wave | quote }}
{{- end -}}
{{- end -}}

{{- define "fel.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "fel.image" -}}
{{- if .digest -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}
