# AWS Deployment Runbook — Job Portal

Documents the steps actually used to deploy this Flask app to a single EC2 instance in `eu-central-1`. Secret values are redacted below — see the "Secrets" section for where they actually live.

## Architecture

One EC2 instance (Amazon Linux 2023, `t3.micro`) running gunicorn behind nginx, with SQLite persisted on its EBS volume. No inbound SSH — management is via AWS Systems Manager Session Manager. App secrets live in SSM Parameter Store and are fetched into a local `.env` file at boot by the instance's IAM role. HTTPS is served via a free Let's Encrypt certificate using a free `sslip.io` hostname (no owned domain required).

| Resource | Value |
|---|---|
| Region | `eu-central-1` |
| VPC | `vpc-068a963b25594826f` (default VPC) |
| Subnet | `subnet-0c452366433e814cc` |
| Security group | `job-portal-web-sg` (`sg-056ec843464ae53f3`) — inbound TCP 80 and 443 from `0.0.0.0/0` |
| AMI | Amazon Linux 2023 x86_64, resolved via SSM public parameter at launch time |
| Instance | `i-08c67938c406f8608` (`t3.micro`) |
| Public IP | `63.177.108.149` |
| HTTPS hostname | `63-177-108-149.sslip.io` (free wildcard DNS pointing at the IP) — this is the only hostname the TLS cert is valid for; the bare IP over HTTPS will show a certificate warning |
| IAM role | `job-portal-ec2-role` |
| Instance profile | `job-portal-ec2-profile` |
| S3 bucket (deploy package) | `job-portal-deploy-127555670611-eu-central-1` |
| SSM parameter prefix | `/job-portal/*` |

## Prerequisites

- AWS CLI v2 installed and authenticated (`aws sts get-caller-identity` works)
- A default VPC with a public subnet in the target region
- App code with `requirements.txt` including `gunicorn`

## 1. Code changes required before deploying

- `db.create_all()` must run at **module import time**, not inside `if __name__ == '__main__':` — gunicorn imports the module but never executes that block, so tables would never get created otherwise.
- Add `gunicorn` to `requirements.txt`.

## 2. Package the app

Zip the source, excluding the virtualenv, local SQLite DB, and local secrets:

```bash
cd "job portals"
zip -r app.zip . \
  -x "venv/*" -x "__pycache__/*" -x "*/__pycache__/*" \
  -x "instance/*" -x ".env" -x ".git/*" -x "*.pyc"
```

## 3. Create a private S3 bucket for the deploy package

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="job-portal-deploy-${ACCOUNT_ID}-eu-central-1"

aws s3api create-bucket --bucket "$BUCKET" --region eu-central-1 \
  --create-bucket-configuration LocationConstraint=eu-central-1

aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3 cp app.zip "s3://$BUCKET/app.zip"
```

## 4. Store secrets in SSM Parameter Store

Sensitive values (`SECRET_KEY`, `MAIL_PASSWORD`) use `SecureString`; the rest use plain `String`. **Never** put these in user data — they're fetched at boot via the instance's IAM role instead.

```bash
aws ssm put-parameter --name /job-portal/SECRET_KEY     --type SecureString --value "<redacted>" --region eu-central-1
aws ssm put-parameter --name /job-portal/MAIL_SERVER     --type String       --value "smtp.gmail.com" --region eu-central-1
aws ssm put-parameter --name /job-portal/MAIL_PORT       --type String       --value "587" --region eu-central-1
aws ssm put-parameter --name /job-portal/MAIL_USERNAME   --type String       --value "<redacted>" --region eu-central-1
aws ssm put-parameter --name /job-portal/MAIL_PASSWORD   --type SecureString --value "<redacted>" --region eu-central-1
aws ssm put-parameter --name /job-portal/MAIL_USE_TLS    --type String       --value "true" --region eu-central-1
aws ssm put-parameter --name /job-portal/MAIL_DEFAULT_SENDER --type String   --value "<redacted>" --region eu-central-1
```

Note: the production `SECRET_KEY` is deliberately different from the local dev `.env` value, so server sessions and local sessions never collide.

## 5. IAM role and instance profile (least privilege)

Trust policy (`trust-policy.json`) — only EC2 can assume this role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}
  ]
}
```

App access policy (`app-access-policy.json`) — scoped to exactly this bucket object and this app's parameters:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadDeployPackage",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::job-portal-deploy-127555670611-eu-central-1/app.zip"
    },
    {
      "Sid": "ReadAppParameters",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParametersByPath"],
      "Resource": "arn:aws:ssm:eu-central-1:127555670611:parameter/job-portal/*"
    },
    {
      "Sid": "DecryptSecureStrings",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:eu-central-1:127555670611:alias/aws/ssm"
    }
  ]
}
```

```bash
aws iam create-role --role-name job-portal-ec2-role \
  --assume-role-policy-document file://trust-policy.json

aws iam put-role-policy --role-name job-portal-ec2-role \
  --policy-name job-portal-app-access \
  --policy-document file://app-access-policy.json

# Grants Session Manager access (no SSH keys needed)
aws iam attach-role-policy --role-name job-portal-ec2-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

aws iam create-instance-profile --instance-profile-name job-portal-ec2-profile

aws iam add-role-to-instance-profile --instance-profile-name job-portal-ec2-profile \
  --role-name job-portal-ec2-role
```

## 6. Security group

HTTP only, no SSH — management is via Session Manager instead:

```bash
VPC_ID="vpc-068a963b25594826f"

SG_ID=$(aws ec2 create-security-group --group-name job-portal-web-sg \
  --description "Job portal web app - HTTP only inbound" \
  --vpc-id "$VPC_ID" --region eu-central-1 --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region eu-central-1
```

## 7. Find subnet and AMI

```bash
# Any public subnet (auto-assigns a public IP) in the default VPC
aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID Name=map-public-ip-on-launch,Values=true \
  --region eu-central-1 --query 'Subnets[0].{SubnetId:SubnetId,AZ:AvailabilityZone}'

# Latest Amazon Linux 2023 AMI, resolved via public SSM parameter (avoids hardcoding an AMI ID)
aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --region eu-central-1 --query 'Parameter.Value' --output text
```

## 8. Boot script (`userdata.sh`)

Runs once at first boot via cloud-init. Installs Python 3.11 + nginx, pulls the app from S3, builds a venv, writes `.env` from SSM parameters (values are fetched at runtime by the instance role — never embedded in this script), and sets up gunicorn + nginx as systemd services.

```bash
#!/bin/bash
set -e
exec > /var/log/job-portal-bootstrap.log 2>&1

dnf update -y
dnf install -y python3.11 python3.11-pip nginx unzip

APP_DIR=/opt/job-portal
mkdir -p "$APP_DIR"

aws s3 cp s3://job-portal-deploy-127555670611-eu-central-1/app.zip /tmp/app.zip --region eu-central-1
unzip -o /tmp/app.zip -d "$APP_DIR"

cd "$APP_DIR"
python3.11 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

aws ssm get-parameters-by-path --path /job-portal/ --with-decryption --region eu-central-1 \
  --query 'Parameters[].[Name,Value]' --output text | while IFS=$'\t' read -r name value; do
    key=$(basename "$name")
    echo "${key}=${value}" >> "$APP_DIR/.env"
done
chmod 600 "$APP_DIR/.env"

useradd -r -s /sbin/nologin jobportal || true
chown -R jobportal:jobportal "$APP_DIR"

cat > /etc/systemd/system/job-portal.service << 'UNITEOF'
[Unit]
Description=Job Portal Flask app (gunicorn)
After=network.target

[Service]
User=jobportal
Group=jobportal
WorkingDirectory=/opt/job-portal
ExecStart=/opt/job-portal/venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable job-portal
systemctl start job-portal

# Replace the stock nginx.conf's inline default server with a conf.d-only
# setup, so our server block is the only one bound to port 80.
cat > /etc/nginx/nginx.conf << 'NGINXCONFEOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;

include /usr/share/nginx/modules/*.conf;

events {
    worker_connections 1024;
}

http {
    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                       '$status $body_bytes_sent "$http_referer" '
                       '"$http_user_agent" "$http_x_forwarded_for"';

    access_log  /var/log/nginx/access.log  main;

    sendfile            on;
    tcp_nopush          on;
    keepalive_timeout   65;
    types_hash_max_size 4096;

    include             /etc/nginx/mime.types;
    default_type        application/octet-stream;

    include /etc/nginx/conf.d/*.conf;
}
NGINXCONFEOF

cat > /etc/nginx/conf.d/job-portal.conf << 'SITEEOF'
server {
    listen 80;
    server_name _;

    location /static/ {
        alias /opt/job-portal/static/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
SITEEOF

systemctl enable nginx
systemctl start nginx
```

## 9. Launch the instance

IMDSv2 enforced (blocks SSRF-based credential theft), EBS encrypted, no key pair (SSM-only access):

```bash
aws ec2 run-instances \
  --region eu-central-1 \
  --image-id ami-0276cae04a46a8438 \
  --instance-type t3.micro \
  --subnet-id subnet-0c452366433e814cc \
  --security-group-ids sg-056ec843464ae53f3 \
  --iam-instance-profile Name=job-portal-ec2-profile \
  --associate-public-ip-address \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":8,"VolumeType":"gp3","Encrypted":true,"DeleteOnTermination":true}}]' \
  --user-data file://userdata.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=job-portal},{Key=managed_by,Value=claude-code}]'
```

```bash
aws ec2 wait instance-running --region eu-central-1 --instance-ids i-08c67938c406f8608

aws ec2 describe-instances --region eu-central-1 --instance-ids i-08c67938c406f8608 \
  --query 'Reservations[0].Instances[0].{State:State.Name,PublicIp:PublicIpAddress}'
```

Boot takes a few minutes after the instance reaches `running` (package installs + pip install). Bootstrap log: `/var/log/job-portal-bootstrap.log` on the instance.

## 10. Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://<public-ip>/
curl -s http://<public-ip>/ | grep -E "<h1>|<title>"
```

(HTTPS verification is in section 11, after the cert is issued.)

## 11. HTTPS — free cert via sslip.io + Let's Encrypt

Let's Encrypt won't issue a certificate for a bare IP address — it needs a hostname to validate against. `sslip.io` is a free wildcard DNS service with no signup: `63-177-108-149.sslip.io` automatically resolves to `63.177.108.149` (the IP is parsed straight out of the hostname), which is enough for Let's Encrypt's HTTP-01 challenge to succeed.

### Open port 443

```bash
aws ec2 authorize-security-group-ingress --group-id sg-056ec843464ae53f3 \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 --region eu-central-1
```

### Point nginx at the sslip.io hostname

Certbot's nginx plugin edits the config by matching `server_name`, so this needs to be set before running certbot (via Session Manager or `aws ssm send-command`):

```bash
sed -i "s/server_name _;/server_name 63-177-108-149.sslip.io;/" /etc/nginx/conf.d/job-portal.conf
nginx -t && systemctl reload nginx
```

### Install certbot (isolated venv — AL2023 has no native package)

```bash
python3.11 -m venv /opt/certbot
/opt/certbot/bin/pip install --upgrade pip
/opt/certbot/bin/pip install certbot certbot-nginx
ln -sf /opt/certbot/bin/certbot /usr/bin/certbot
```

### Request the certificate

The `--nginx` plugin edits the nginx config itself — adds the HTTPS server block and an HTTP→HTTPS redirect — with no downtime (no need to stop nginx):

```bash
certbot --nginx -d 63-177-108-149.sslip.io --non-interactive --agree-tos \
  -m <your-email> --redirect
```

Certificate and key land at `/etc/letsencrypt/live/63-177-108-149.sslip.io/`. Valid 90 days.

### Set up auto-renewal

The pip-installed certbot doesn't wire up renewal automatically (that's normally bundled with the OS package) — add a systemd timer:

```bash
cat > /etc/systemd/system/certbot-renew.service << 'EOF'
[Unit]
Description=Certbot Renewal

[Service]
Type=oneshot
ExecStart=/opt/certbot/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"
EOF

cat > /etc/systemd/system/certbot-renew.timer << 'EOF'
[Unit]
Description=Twice daily certbot renewal check

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now certbot-renew.timer
```

Test the renewal path without actually renewing (doesn't count against Let's Encrypt rate limits):

```bash
/opt/certbot/bin/certbot renew --dry-run
```

### Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://63-177-108-149.sslip.io/
curl -sv https://63-177-108-149.sslip.io/ 2>&1 | grep -E "subject:|issuer:|SSL certificate"
```

### Important caveat

**Always use `https://63-177-108-149.sslip.io/`, not `https://63.177.108.149/`.** The certificate's Common Name is the sslip.io hostname, not the IP — visiting the bare IP over HTTPS will trip a "not secure" / certificate-mismatch warning in the browser even though the server is configured correctly. If the instance's public IP ever changes (e.g. after a stop/start without an Elastic IP), the sslip.io hostname changes with it and the certificate needs to be reissued for the new one.

`sslip.io` is a third-party free service, not AWS-operated — a low but real dependency: if it ever goes down, both DNS resolution and certificate renewal (HTTP-01 re-validates the hostname each time) would break until it's back or you switch to an owned domain.

## Managing the running instance

No SSH — connect via Session Manager:

```bash
aws ssm start-session --target i-08c67938c406f8608 --region eu-central-1
```

Common on-instance commands:

```bash
sudo systemctl status job-portal     # app service
sudo systemctl restart job-portal    # after a code/config change
sudo journalctl -u job-portal -f     # tail app logs
sudo tail -f /var/log/job-portal-bootstrap.log   # boot script log
sudo tail -f /var/log/nginx/error.log
```

## Redeploying after a code change

1. Re-zip and re-upload: `zip -r app.zip . -x "venv/*" ... && aws s3 cp app.zip s3://job-portal-deploy-127555670611-eu-central-1/app.zip`
2. Via Session Manager on the instance:
   ```bash
   sudo aws s3 cp s3://job-portal-deploy-127555670611-eu-central-1/app.zip /tmp/app.zip --region eu-central-1
   sudo unzip -o /tmp/app.zip -d /opt/job-portal
   cd /opt/job-portal && sudo -u jobportal venv/bin/pip install -r requirements.txt
   sudo systemctl restart job-portal
   ```

## Known limitations / follow-ups

- **No stable IP** — the public IP changes if the instance is stopped/started, which breaks both the sslip.io hostname and the HTTPS certificate (issued for the old IP's hostname). An Elastic IP fixes this (still billed hourly under AWS's public-IPv4 pricing, whether Elastic or auto-assigned).
- **Single instance** — no auto-scaling, no managed database, no load balancer. Deliberate tradeoff for cost/simplicity given SQLite's single-writer, single-file nature.
- Secrets are re-read from SSM only at boot (written into `.env`); rotating an SSM parameter requires a re-run of that section of the boot script (or an instance reboot) to take effect.
- HTTPS depends on the free `sslip.io` service staying up (see the caveat at the end of section 11) — an owned domain removes that dependency.

## Estimated cost

Roughly $8-12/month: `t3.micro` (~$7.60/mo on-demand, $0 if within free tier), ~8GB gp3 EBS (~$0.64/mo), public IPv4 (~$3.60/mo), S3 + SSM Standard tier (negligible).
