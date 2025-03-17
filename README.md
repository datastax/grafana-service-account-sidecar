# Grafana Service Accounts Sidecar

## Description

This sidecar can be deployed alongside the [Grafana Helm chart](https://github.com/grafana/helm-charts/tree/main/charts/grafana). It is used to provision service accounts and automatically create secrets on Grafana deployments that do not use persistence. 

We need this since there is currently no option in the grafana operator deployment parameters to provision service accounts. And since Grafana is currently deployed in serverless without any persistence, any restart to the pod would cause any created service accounts to be lost. 

This sidecar is a solution that will create the service account when the grafana pod is restarted. It is checking every `CHECK_INTERVAL_IN_S` for the existence of that SA in case grafana gets restarted and it is lost. 

It will create the service account and store its token in a particular secret. (This might be optimized to create multiple service accounts if needed)

Note: Once this feature becomes a reality, we will no longer need this sidecar: [Grafana Provision Service Accounts Feature Request](https://github.com/grafana/grafana-operator/issues/1469)
## Usage


To deploy the sidecar, you can use the `extraContainers` stanza from the Grafana Helm chart.

```yaml
grafana:
  extraContainers: |
    - name: grafana-service-account-sc
      image: datastax/grafana-service-accounts-sidecar:<sha>
      imagePullPolicy: IfNotPresent
      env:
        - name: GRAFANA_USERNAME
          value: "admin"
        - name: GRAFANA_PASSWORD
          value: "prom-operator"
        - name: GRAFANA_URL
          value: "http://127.0.0.1:3000"
        - name: K8S_NAMESPACE
          value: "monitor"
        - name: TOKEN_SECRET_NAME
          value: "grafana-service-account-token"
        - name: SERVICE_ACCOUNT_NAME
          value: "Provisioned-SA"
        - name: TOKEN_NAME
          value: "token1"
        - name: CHECK_INTERVAL_IN_S
          value: "60"
```

Access to Grafana is specified through `GRAFANA_URL`, `GRAFANA_USERNAME`, and `GRAFANA_PASSWORD`.

You will also need to provide the namespace for the secret through `K8S_NAMESPACE` (The same as Grafana's namespace)

You can specify the names of things such as the Service Account `SERVICE_ACCOUNT_NAME`, the Token `TOKEN_NAME`, and the Secret for the Token `TOKEN_SECRET_NAME`. Although these are all optional, it is recommended that you do override the default values though.

The sidecar will ensure the existence of the token and service account every `CHECK_INTERVAL_IN_S`

In order to enable the sidecar to have sufficient permissions to update and create secrets, it needs to be associated with a kubernetes service account.
This means that in your spec for your sidecar deployment, you need to specify a service account like so:
```yaml
    spec:
      serviceAccountName: grafana-sidecar-sa
      containers:
        - name: grafana-service-accounts-sc
        ...
```
If you are deploying this sidecar as an extra container like explained above ^ then you need to define the serviceAccountName on the grafana deployment spec.

The service account should be created with the following permissions and role bindings:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: grafana-sidecar-sa
  namespace: monitor

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: monitor
  name: grafana-sidecar-role
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get", "list", "create", "update", "patch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: grafana-sidecar-rolebinding
  namespace: monitor
subjects:
- kind: ServiceAccount
  name: grafana-sidecar-sa
  namespace: monitor
roleRef:
  kind: Role
  name: grafana-sidecar-role
  apiGroup: rbac.authorization.k8s.io
```


## Docker Image

The image is hosted in 237073351946.dkr.ecr.us-east-1.amazonaws.com/datastax/grafana-service-accounts-sidecar (AWS DMC Cloud-Tools). We deploy it using a GitHub action workflow.

For that workflow to function you need to have the ECR repository created upfront, together with an IAM user that has the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PushAndPull",
            "Effect": "Allow",
            "Action": [
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:CompleteLayerUpload",
                "ecr:UploadLayerPart",
                "ecr:InitiateLayerUpload",
                "ecr:BatchCheckLayerAvailability",
                "ecr:PutImage"
            ],
            "Resource": "arn:aws:ecr:<region>:<account>:repository/<repositoryName>"
        },
        {
            "Sid": "GetAuthorizationToken",
            "Effect": "Allow",
            "Action": [
                "ecr:GetAuthorizationToken"
            ],
            "Resource": "*"
        }
    ]
}
```

## Local Minikube Example

### Prerequisite
Have [minikube](https://minikube.sigs.k8s.io/docs/start/?arch=%2Flinux%2Fx86-64%2Fstable%2Fbinary+download) installed.
Have [helm](https://helm.sh/docs/intro/install/) installed with the grafana repo added.

### Steps
To run this locally to test it on minikube, we have provided the `rbac.yaml`, and `sidecar.yaml` files in the local-test folder.

- Build the docker image in the minikube docker environment:
  - ```bash
    eval $(minikube -p minikube docker-env)
    docker build -t grafana-service-accounts-sidecar:local .
- Create a `monitor` namespace and apply both `rbac.yaml` and `sidecar.yaml`
  - ```bash
     kubectl create namespace monitor
     kubectl apply -f rbac.yaml
     kubectl apply -f sidecar.yaml

You should be good, give it a minute and check the secrets for the `grafana-service-account-token` that was created (in the monitor namespace).

You can also Port forward your grafana installation and check for the service account there. You should see something like this:

![Service Account Example](/docs-resources/Service_account_example_sc.png)

![Service Account Token Example](/docs-resources/Service_account_token_example_sc.png)