-- 新数据卷初始化时复用已有 volume 的幂等语义模型建表迁移。
SOURCE /docker-entrypoint-initdb.d/migrations/20261001_10_semantic_model.sql;
SOURCE /docker-entrypoint-initdb.d/migrations/20261001_12_semantic_metric_relations.sql;
