# Kubernetes Deployment

Lightweight k3d-based Kubernetes deployment.

## Quick Start

```bash
../scripts/k8s/deploy-k8s.sh # Deploy everything
```

Auto-installs dependencies, creates cluster, builds images, deploys services, loads seed data.

## Commands

```bash
../scripts/k8s/deploy-k8s.sh              # Deploy
../scripts/k8s/deploy-k8s.sh rebuild      # Rebuild images
../scripts/k8s/deploy-k8s.sh status       # Status & URLs
../scripts/k8s/deploy-k8s.sh test         # Test endpoints
../scripts/k8s/deploy-k8s.sh fix          # Restart failed pods
../scripts/k8s/deploy-k8s.sh logs gateway # View logs
../scripts/k8s/deploy-k8s.sh stop         # Stop cluster
../scripts/k8s/deploy-k8s.sh start        # Start cluster
../scripts/k8s/deploy-k8s.sh delete       # Delete cluster
```

## Access URLs

- Gateway: http://localhost:30080
- Swagger: http://localhost:30080/swagger
- GraphQL: http://localhost:30080/graphql
- Dashboard: http://localhost:30008

## Configuration

```
k8s/
├── postgres-deployment.yaml  # PostgreSQL + PVC
├── redis-deployment.yaml     # Redis cache
├── services-deployment.yaml  # 8 microservices
└── seed-job.yaml             # Data seeding
```

## Troubleshooting

### Check Pods
```bash
kubectl get pods -n eci-platform
kubectl describe pod <pod-name> -n eci-platform
kubectl logs <pod-name> -n eci-platform
../scripts/k8s/deploy-k8s.sh fix
```

### Common Issues
- Gateway 401: Access http://localhost:30080/docs directly
- Pods pending: Increase cluster resources
- Image pull errors: Run `../scripts/k8s/deploy-k8s.sh rebuild`

## kubectl Commands

```bash
kubectl get all -n eci-platform
kubectl exec -n eci-platform -it deployment/gateway -- /bin/sh
kubectl port-forward -n eci-platform deployment/gateway 8080:8000
kubectl scale deployment customers --replicas=2 -n eci-platform
```

## Requirements

- Docker
- 4GB+ RAM
- 2+ CPU cores
