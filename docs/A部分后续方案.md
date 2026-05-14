# A 部分后续执行方案 — 日志采集与传输 + 基础设施

---

## Step 1：规划 Kafka Topic（优先）

### 执行步骤

1. 关闭 Kafka 自动创建 Topic，在 docker-compose.yml 中改为：
   ```yaml
   KAFKA_AUTO_CREATE_TOPICS_ENABLE: "false"
   ```

2. 编写 Topic 初始化脚本 `scripts/init-topics.sh`：
   ```bash
   #!/bin/bash
   KAFKA_BIN="/opt/kafka/bin"
   BOOTSTRAP="localhost:9092"
   
   for TOPIC in vpn-logs-raw oa-logs-raw api-logs-raw system-logs-raw; do
     $KAFKA_BIN/kafka-topics.sh --create \
       --bootstrap-server $BOOTSTRAP \
       --topic $TOPIC \
       --partitions 3 \
       --replication-factor 1 \
       --if-not-exists
   done
   
   # 设置保留策略：7 天
   for TOPIC in vpn-logs-raw oa-logs-raw api-logs-raw system-logs-raw; do
     $KAFKA_BIN/kafka-configs.sh --alter \
       --bootstrap-server $BOOTSTRAP \
       --entity-type topics --entity-name $TOPIC \
       --add-config retention.ms=604800000
   done
   ```

3. 执行脚本，验证 Topic 创建成功：
   ```bash
   docker exec kafka /opt/kafka/bin/kafka-topics.sh \
     --bootstrap-server localhost:9092 --list
   ```

4. 输出一份 Topic 设计表给组员：

   | Topic 名称 | 用途 | 分区 | 消息格式 | 保留时间 |
   |------------|------|------|----------|----------|
   | `vpn-logs-raw` | VPN 登录日志 | 3 | JSON/UTF-8 | 7 天 |
   | `oa-logs-raw` | OA 系统日志 | 3 | JSON/UTF-8 | 7 天 |
   | `api-logs-raw` | API 访问日志 | 3 | JSON/UTF-8 | 7 天 |
   | `system-logs-raw` | 系统日志 | 3 | JSON/UTF-8 | 7 天 |

### 怎么学

- 官方文档：[Kafka Topic 配置项](https://kafka.apache.org/37/documentation.html#topicconfigs) — 重点看 `retention.ms`、`max.message.bytes`、`num.partitions`
- 命令行速查：[Kafka CLI Quick Start](https://kafka.apache.org/37/documentation.html#quickstart) — 掌握 `kafka-topics.sh` 的 `--create`、`--describe`、`--list`
- 实操建议：直接在容器里敲命令练，`docker exec -it kafka bash` 进去操作

---

## Step 2：完善 Filebeat 采集配置

### 执行步骤

1. 创建 `filebeat/filebeat.yml`（docker-compose 已经挂载了这个路径，但文件可能还没写）：

   ```yaml
   filebeat.inputs:
     - type: log
       enabled: true
       paths:
         - /var/log/app/vpn_logs.log
       fields:
         log_type: vpn
         env: dev
       fields_under_root: true

   # 如果后续有其他日志源，追加 input：
   #  - type: log
   #    enabled: true
   #    paths:
   #      - /var/log/app/oa_logs.log
   #    fields:
   #      log_type: oa
   #      env: dev
   #    fields_under_root: true

   output.kafka:
     hosts: ["kafka:9092"]
     topic: "vpn-logs-raw"
     # 如果有多种日志源，用动态 Topic：
     # topic: '%{[log_type]}-logs-raw'
     codec.json:
       pretty: false
     required_acks: 1
     compression: gzip

   processors:
     - add_host_metadata: ~
     - drop_fields:
         fields: ["agent", "ecs", "input"]
         ignore_missing: true
   ```

2. 重启 Filebeat 使配置生效：
   ```bash
   docker compose restart filebeat
   ```

3. 验证 Kafka 中收到的消息格式：
   ```bash
   docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic vpn-logs-raw \
     --from-beginning --max-messages 3
   ```
   确认消息是 JSON 格式，包含 `log_type`、`env` 等字段，不包含 `agent`、`ecs` 等无用字段。

### 怎么学

- 官方文档：[Filebeat Log Input](https://www.elastic.co/guide/en/beats/filebeat/8.13/filebeat-input-log.html) — 重点看 `fields`、`multiline`、`exclude_lines`
- 官方文档：[Filebeat Kafka Output](https://www.elastic.co/guide/en/beats/filebeat/8.13/kafka-output.html) — 重点看 `topic`（支持动态模板）、`codec`、`compression`
- 官方文档：[Filebeat Processors](https://www.elastic.co/guide/en/beats/filebeat/8.13/filtering-and-enhancing-data.html) — 了解 `drop_fields`、`add_host_metadata`
- 调试技巧：先把 output 改成 `output.console`（输出到终端），确认格式正确后再切回 Kafka

---

## Step 3：补全 Docker Compose 环境，确保全组可用

### 执行步骤

1. 给 Logstash 和 Flink 补上健康检查，编辑 `docker-compose.yml`：

   ```yaml
   logstash:
     # ... 已有配置 ...
     healthcheck:
       test: ["CMD-SHELL", "curl -f http://localhost:9600/_node/stats || exit 1"]
       interval: 15s
       timeout: 10s
       retries: 5

   flink-jobmanager:
     # ... 已有配置 ...
     healthcheck:
       test: ["CMD-SHELL", "curl -f http://localhost:8081/overview || exit 1"]
       interval: 15s
       timeout: 10s
       retries: 5
   ```

2. 创建 Logstash 占位配置 `logstash/pipeline/logstash.conf`（最简版，后续 B/C 来改）：

   ```ruby
   input {
     kafka {
       bootstrap_servers => "kafka:9092"
       topics => ["vpn-logs-raw"]
       group_id => "logstash-indexer"
       codec => json
     }
   }

   output {
     elasticsearch {
       hosts => ["http://elasticsearch:9200"]
       index => "vpn-logs-%{+YYYY.MM.dd}"
     }
   }
   ```

3. 创建必要的目录结构：
   ```bash
   mkdir -p filebeat logstash/pipeline logs
   ```

4. 全量启动并验证：
   ```bash
   docker compose up -d
   docker compose ps          # 确认所有服务 healthy
   docker compose logs -f     # 观察有无报错
   ```

5. 验证容器间网络联通：
   ```bash
   # Filebeat 能连 Kafka
   docker exec filebeat curl -s kafka:9092 || echo "TCP OK"
   
   # Logstash 能连 ES
   docker exec logstash curl -s http://elasticsearch:9200/_cluster/health
   ```

### 怎么学

- 官方文档：[Docker Compose - depends_on](https://docs.docker.com/compose/how-tos/startup-order/) — 理解 `condition: service_healthy` 的作用
- 官方文档：[Logstash Kafka Input](https://www.elastic.co/guide/en/logstash/8.13/plugins-inputs-kafka.html) — 写占位配置时参考
- 实操建议：反复 `docker compose down && docker compose up -d`，练到闭眼能排查启动失败的原因

---

## Step 4：写消费验证脚本，与 B/C 联调

### 执行步骤

1. 编写 `scripts/verify_consumer.py`：

   ```python
   from kafka import KafkaConsumer
   import json

   consumer = KafkaConsumer(
       'vpn-logs-raw',
       bootstrap_servers='localhost:9092',
       auto_offset_reset='earliest',
       group_id='verify-test',
       value_deserializer=lambda m: json.loads(m.decode('utf-8'))
   )

   print("等待消息...")
   count = 0
   for msg in consumer:
       print(f"[partition={msg.partition} offset={msg.offset}]")
       print(json.dumps(msg.value, indent=2, ensure_ascii=False))
       count += 1
       if count >= 3:
           break

   consumer.close()
   print(f"\n验证完成，共消费 {count} 条消息")
   ```

2. 运行脚本确认数据正常：
   ```bash
   python scripts/verify_consumer.py
   ```

3. 和 B 对齐以下内容（直接发消息或开个短会）：
   - Kafka 消息的 JSON 字段有哪些？（把一条样例消息发给 B）
   - 时间戳格式是什么？（`2026-04-01 09:40:16`）
   - 编码是 UTF-8 吗？（是）
   - B 的 Flink Consumer Group 叫什么？（建议 `flink-processor`）
   - C 的 Logstash Consumer Group 叫什么？（建议 `logstash-indexer`）

4. 整理一份 Kafka 调试命令速查，发给全组：

   ```bash
   # 查看 Topic 列表
   docker exec kafka /opt/kafka/bin/kafka-topics.sh \
     --bootstrap-server localhost:9092 --list
   
   # 查看某个 Topic 的详情
   docker exec kafka /opt/kafka/bin/kafka-topics.sh \
     --bootstrap-server localhost:9092 --describe --topic vpn-logs-raw
   
   # 从头消费 5 条消息（快速验证）
   docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 --topic vpn-logs-raw \
     --from-beginning --max-messages 5
   
   # 查看所有消费者组
   docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
     --bootstrap-server localhost:9092 --list
   
   # 查看某个消费者组的消费进度（看 LAG 列）
   docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
     --bootstrap-server localhost:9092 --group flink-processor --describe
   ```

### 怎么学

- 官方文档：[kafka-python 库](https://kafka-python.readthedocs.io/en/master/apidoc/KafkaConsumer.html) — 重点看 `KafkaConsumer` 的参数
- 官方文档：[Kafka Consumer Groups](https://kafka.apache.org/37/documentation.html#consumerconfigs) — 理解 Consumer Group 的概念，多个 Group 可以独立消费同一 Topic
- 实操建议：开两个终端，一个跑生产者（Filebeat 采集），一个跑消费者脚本，实时看数据流转

---

## Step 5：数据采集监控（前面都做完了再搞）

### 执行步骤

1. 检查消费者组的消费延迟（Lag）：
   ```bash
   docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
     --bootstrap-server localhost:9092 \
     --group flink-processor \
     --describe
   ```
   关注 `LAG` 列：0 表示消费跟得上，持续增长说明下游有问题。

2. 对比日志文件行数和 Kafka 消息数，验证没丢数据：
   ```bash
   # 日志文件行数
   wc -l logs/vpn_logs.log
   
   # Kafka Topic 的消息总数
   docker exec kafka /opt/kafka/bin/kafka-run-class.sh \
     kafka.tools.GetOffsetShell \
     --broker-list localhost:9092 \
     --topic vpn-logs-raw
   ```

3. （可选）写一个一键健康检查脚本 `scripts/healthcheck.sh`：
   ```bash
   #!/bin/bash
   echo "=== Kafka ==="
   docker exec kafka /opt/kafka/bin/kafka-topics.sh \
     --bootstrap-server localhost:9092 --list && echo "OK" || echo "FAIL"
   
   echo "=== Elasticsearch ==="
   curl -s http://localhost:9200/_cluster/health | python3 -c \
     "import sys,json; d=json.load(sys.stdin); print(d['status'])"
   
   echo "=== Flink ==="
   curl -s http://localhost:8081/overview > /dev/null && echo "OK" || echo "FAIL"
   ```

### 怎么学

- 官方文档：[Kafka Monitoring](https://kafka.apache.org/37/documentation.html#monitoring) — 了解 Consumer Lag 的含义
- B 站搜索："Kafka 消费者组 lag 监控" — 有不少实操演示视频
- 实操建议：故意停掉 Flink，观察 Lag 增长；重启后观察 Lag 回落，建立直觉

---

## 执行顺序总结

```
Step 1  Topic 规划        ← 最先做，B/C 等着用
  ↓
Step 2  Filebeat 配置     ← 采集端打磨
  ↓
Step 3  Docker 环境补全   ← 全组基础设施
  ↓
Step 4  消费验证 + 联调   ← 和 B/C 对接
  ↓
Step 5  监控              ← 联调阶段补充
```
