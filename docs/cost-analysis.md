# Cost Analysis: Running This Pipeline on AWS

## What We're Deploying

The full CDC stack: source PostgreSQL, analytics PostgreSQL, Kafka cluster, Debezium connector, Python consumer, and Streamlit dashboard.

## AWS Estimate

| Component | Service | Spec | Monthly Cost |
|-----------|---------|------|-------------|
| Source DB | RDS PostgreSQL | db.t3.micro, 20GB gp3 | ~$15 |
| Analytics DB | RDS PostgreSQL | db.t3.micro, 50GB gp3 | ~$18 |
| Kafka | Amazon MSK | kafka.t3.small x2 brokers, 50GB | ~$30 |
| Debezium | ECS Fargate | 0.5 vCPU, 1GB RAM | ~$15 |
| Consumer | ECS Fargate | 0.25 vCPU, 0.5GB RAM | ~$8 |
| Dashboard | ECS Fargate | 0.25 vCPU, 0.5GB RAM | ~$8 |
| **Total** | | | **~$94/month** |

## Notes

- **MSK is the biggest cost**. Kafka needs at least 2 brokers for durability. At low volume you're paying mostly for the broker instances sitting idle.
- **RDS db.t3.micro** is the free-tier eligible instance. For production traffic, bump to db.t3.small (~$25/month each).
- **Debezium needs decent RAM** because it runs inside Kafka Connect's JVM. 1GB is minimum; production usually needs 2-4GB.
- **No Zookeeper cost on AWS** because MSK manages it internally (or uses KRaft in newer versions).

## GCP Alternative

| Component | Service | Monthly Cost |
|-----------|---------|-------------|
| Source DB | Cloud SQL (db-f1-micro) | ~$10 |
| Analytics DB | Cloud SQL (db-f1-micro) | ~$10 |
| Kafka | Confluent Cloud (Basic) | ~$20 |
| Debezium + Consumer | Cloud Run | ~$15 |
| **Total** | | **~$55/month** |

GCP is cheaper mainly because Confluent Cloud's basic tier handles Kafka + Connect (including Debezium) in one managed service. No need to run your own Debezium container.

## Cost Optimization Ideas

1. **Use Confluent Cloud instead of self-managed Kafka**: eliminates MSK and Debezium container costs. ~$20/month for basic tier at low throughput.
2. **Combine source and analytics into one DB**: saves one RDS instance (~$15). Not ideal architecturally but fine for a small project.
3. **Run consumer on a schedule instead of always-on**: if near-real-time isn't needed, use Lambda triggered by SQS to process events in batches. Drops to ~$2/month for compute.
4. **Free tier**: both AWS and GCP offer 12-month free tiers that cover RDS micro and basic compute. Total drops to ~$30/month (just Kafka).
