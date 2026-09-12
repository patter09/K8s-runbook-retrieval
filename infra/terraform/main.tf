# This mirrors what "kind create cluster" did manually in the previous
# step, but now the cluster's existence is declared as code: `terraform
# apply` creates it, `terraform destroy` tears it down, and `terraform plan`
# shows you exactly what would change before it happens.

resource "kind_cluster" "this" {
  name           = var.cluster_name
  wait_for_ready = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"

      extra_port_mappings {
        container_port = 30080
        host_port       = 8000
      }
      extra_port_mappings {
        container_port = 30090
        host_port       = 9090
      }
      extra_port_mappings {
        container_port = 30030
        host_port       = 3000
      }
    }
  }
}