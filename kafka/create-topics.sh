#!/bin/bash
# Kafka Topic Creation Script
# Run this after Kafka is healthy: docker compose exec kafka bash /kafka/create-topics.sh

set -e

BOOTSTRAP_SERVER="kafka:9092"

echo "🚀 Creating Kafka topics for B2G Microservices..."

# Topic 1: telemetry.raw
echo "📡 Creating topic: telemetry.raw"
kafka-topics --create \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --topic telemetry.raw \
  --partitions 4 \
  --replication-factor 1 \
  --config retention.ms=604800000 \
  --if-not-exists

# Topic 2: forecasting.predictions
echo "🤖 Creating topic: forecasting.predictions"
kafka-topics --create \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --topic forecasting.predictions \
  --partitions 2 \
  --replication-factor 1 \
  --config retention.ms=86400000 \
  --if-not-exists

# Topic 3: mpc.decisions
echo "🎯 Creating topic: mpc.decisions"
kafka-topics --create \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --topic mpc.decisions \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=86400000 \
  --if-not-exists

# Topic 4: derms.dispatch
echo "⚡ Creating topic: derms.dispatch"
kafka-topics --create \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --topic derms.dispatch \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=2592000000 \
  --if-not-exists

# Topic 5: compliance.reports
echo "🛡️ Creating topic: compliance.reports"
kafka-topics --create \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --topic compliance.reports \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=31536000000 \
  --if-not-exists

echo ""
echo "✅ All topics created successfully!"
echo ""
echo "📋 Listing all topics:"
kafka-topics --list --bootstrap-server $BOOTSTRAP_SERVER

echo ""
echo "📊 Topic details:"
for topic in telemetry.raw forecasting.predictions mpc.decisions derms.dispatch compliance.reports; do
  echo ""
  echo "Topic: $topic"
  kafka-topics --describe --bootstrap-server $BOOTSTRAP_SERVER --topic $topic
done
