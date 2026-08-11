# Deploy using Docker and AWS ECS-ECR

1. Create Dockerfile which has command to run app
2. Test it on local - `docker run --rm -p 8000:8000 <_local_image_name:tag_>`
3. Create ecr cluster with fargate
4. Create task definition
5. Create service with your task definition
6. Login to aws-ecr - `aws ecr get-login-password --region <_region_> | docker login --username AWS --password-stdin <_aws_account_id_>.dkr.ecr.<_region_>.amazonaws.com`
7. Create ECR repository - `aws ecr create-repository --repository-name <_repo_name_> --region <_region_>`
8. Push docker image to ecr - `docker push <_aws_account_id_>.dkr.ecr.<_region_>.amazonaws.com/<_local_image_name:tag_>` // <_repo_name_:tag\_> need same as local_image_name:tag
9. Create local image with ECR repo matching - `docker tag <_ai-agent:prod_> 577267183964.dkr.ecr.ap-south-1.amazonaws.com/<_ai-agent:prod_>` -> Push the local ai-agent:prod image to the ai-agent repository in my AWS ECR registry ( docker push <_aws_account_id_>.dkr.ecr.<_region_>.amazonaws.com/<_local_image_name:tag_> )
10. If you are passing env vars from compose.yml then run - `docker run --rm --env-file .env -p 8000:8000 ai-agent:prod`
11. if yes step 7. -> Create secrets AWS Secrets Manager - `aws secretsmanager create-secret --name prod/ai-agent/<_secret_name_> --secret-string <_secret_value_>  --region <_region_>`
12. Update ECS task definition so ECS supplies the same secret variables
    1. Create new revision of task definition with json ( create of step 5. revision )
    2. also Add container port mapping in task definition
        ```json
        "containerDefinitions": [
        {
            "portMappings": [
            {
                "containerPort": 8000, //app running port
                "hostPort": 8000, // exposing port
                "protocol": "tcp",
                "name": "fastapi-8000",
                "appProtocol": "http"
            }
            ]
        }
        ]
        ```
    3. add
        ```json
        "secrets": [
            {
            "name": "env_var_key_which_in_actual_code",
            "valueFrom": "secret_arn"
            },
        ]
        ```
    4. Give ECS permission to read the secrets
        - Find your task execution role - `aws ecs describe-task-definition \ --task-definition YOUR_TASK_DEFINITION \ --region ap-south-1 \ --query 'taskDefinition.executionRoleArn'`
    5. attach a policy to that role allowing -
        ```json
        {
            "Effect": "Allow",
            "Action": ["secretsmanager:GetSecretValue"],
            "Resource": [
                "arn:aws:secretsmanager:ap-south-1:577267183964:secret:prod/ai-agent/*"
            ]
        }
        ```
    6. Create/register a new revision containing the secrets. ( which is point 1 + 2)
    7. Verify the deployment
13. if still not able to access check security group inbound rules and your port exposing inbound rule
