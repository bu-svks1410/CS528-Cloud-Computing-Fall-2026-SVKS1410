PROJECT_ID="cultivated-link-508221-e6"
REGION="us-central1"
ZONE="us-central1-a"
BUCKET_NAME="cultivated-link-508221-e6-cs528-hw2"

SERVER_VM="hw5-server"
SUBSCRIBER_VM="hw5-subscriber"
CLIENT_VM="hw5-client"

SERVER_MACHINE="e2-small"
SUBSCRIBER_MACHINE="e2-micro"
CLIENT_MACHINE="e2-small"

SERVER_SA="hw5-server-sa"
SUBSCRIBER_SA="hw5-subscriber-sa"
MONITOR_SA="hw5-monitor-sa"

SQL_INSTANCE="hw5-postgres"
SQL_DATABASE="hw5"
SQL_USER="hw5_app"
SQL_VERSION="POSTGRES_16"
SQL_EDITION="ENTERPRISE"
SQL_TIER="db-f1-micro"

TOPIC_ID="hw5-forbidden-requests"
SUBSCRIPTION_ID="hw5-forbidden-requests-sub"
SUBSCRIBER_LOG_OBJECT="hw4-logs/hw5-forbidden-requests.jsonl"

SERVER_IP_NAME="hw5-server-ip"
HTTP_FIREWALL="hw5-allow-http"
SSH_FIREWALL="hw5-allow-iap-ssh"
MONITOR_FUNCTION="hw5-sql-monitor"
PORT="8080"

CLIENT_SA="hw5-client-sa"
BUILD_SA="hw5-build-sa"
BUNDLE_BUCKET="${PROJECT_ID}-hw5-deploy"
BUNDLE_OBJECT="deployment/hw5.tar.gz"
SQL_SECRET="hw5-db-password"
