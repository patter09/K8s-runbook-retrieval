output "cluster_name" {
  value = kind_cluster.this.name
}

output "kubeconfig_path" {
  value       = kind_cluster.this.kubeconfig_path
  description = "Path to the kubeconfig file for this cluster. Use with: export KUBECONFIG=<this path>"
}

output "endpoint" {
  value = kind_cluster.this.endpoint
}