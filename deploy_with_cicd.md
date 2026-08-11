1. Create Docker file
2. ECR login
3. Create ECR repository console/CLI - CLI
    - Create `aws ecr create-repository \ --repository-name <_repo_name_> \ --region <_region_>`
    - verify `aws ecr describe-repositories \ --repository-name <_repo_name_> \ --region <_region_>`
4. Create ECS cluster - `aws ecs create-cluster \ --cluster-name <_cluster_name_> \ --region <_region_>`
5. Create ECS task definition - You can create from aws console - it needs - first create with any sample image
    ```
    CPU
    Memory
    Container
    ECR image
    Port 8000
    Environment
    Secrets
    Execution role
    Task role
    ```
    ```json
    JSON version ( IMP keys)
    {
    "requiresCompatibilities": [
        "FARGATE"
    ],
    "containerDefinitions": [
        {
        "name": "fastapi-ai_agent",
        "image": "",
        "essential": true,
        "portMappings": [ // exposing port
            {
            "containerPort": 8000,
            "protocol": "tcp"
            }
        ],
        "environment": [
            {
            "name": "ENVIRONMENT",
            "value": "production"
            }
        ],
        "secrets": [
            {
            "name": "DATABASE_URL",
            "valueFrom": "YOUR_DATABASE_SECRET_ARN"
            }
        ]
        }
    ]
    }
    ```
6. Secrets Manager - direct add to task definition or Create aws secrets CLI: `aws secretsmanager create-secret \ --name ai-agent/prod/database-url \ --secret-string 'YOUR_DATABASE_URL' \ --region ap-south-1`
7. Create execution role - ECS execution role needs to be able to:
    1. Read Secrets Manager
    2. AmazonECSTaskExecutionRolePolicy
8. ECS service - launch type, desire container count etc

### below steps need when AWS authentication via OIDC.

9. Create GitHub OIDC - Create an IAM OIDC provider for: Create an IAM OIDC provider for:
    - Go to: IAM → Identity providers → Add provider
    - select OpenID Connect
    - provider URL enter - https://token.actions.githubusercontent.com
    - Audience enter - sts.amazonaws.com
10. Create GitHub deployment IAM role -
    - go to IAM → Roles → Create role
    - Under Trusted entity type, select: Web identity
    - select provider and audience
    - enter github organization name or individual username -> Create
    ```json
    Example
    {
    "Version": "2012-10-17",
    "Statement": [
        {
        "Effect": "Allow",
        "Principal": {
            "Federated": "arn:aws:iam::577267183964:oidc-provider/token.actions.githubusercontent.com"
        },
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {
            "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
            },
            "StringLike": {
            "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/YOUR_REPOSITORY:ref:refs/heads/main"
            }
        }
        }
    ]
    }
    ```
11. Give GitHub role ECR permissions
    - Go to : roles - Permissions → Add permissions → Create inline policy → JSON
    ```json
    {
        "Statement": [
            {
                "Sid": "ECRAuth",
                "Effect": "Allow",
                "Action": ["ecr:GetAuthorizationToken"],
                "Resource": "*"
            },
            {
                "Sid": "ECRPush",
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:CompleteLayerUpload",
                    "ecr:InitiateLayerUpload",
                    "ecr:PutImage",
                    "ecr:UploadLayerPart"
                ],
                "Resource": "ecr-repo-arn"
            }
        ]
    }
    ```
12. Add GitHub secret - add `AWS_DEPLOY_ROLE_ARN` - you will find this in github role which you created

# instead AWS authentication via OIDC you can use AWS Access Keys in Configure AWS credentials step

    ```
     with:
        role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
        aws-region: ${{ secrets.AWS_REGION }}

    instead with AWS Access Keys as below

    with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: ${{ secrets.AWS_REGION }}
    ```

13. Create GitHub Actions workflow
