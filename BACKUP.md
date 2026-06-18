# 資料庫備份與還原

## 自動備份(已啟用)
`docker-compose.yml` 的 `db-backup` 服務(postgres-backup-local)會自動:
- **每天凌晨 3 點(Asia/Taipei)** 對 `hexagram` 資料庫做 `pg_dump`
- 存到主機 `./backups/`(已加入 `.gitignore`,不會進 git)
- 自動輪替保留:**每日 7 份、每週 4 份、每月 6 份**
- 目錄結構:`backups/daily|weekly|monthly/`,各有 `hexagram-latest.sql.gz` 指向最新

> 注意:這個映像產出的 `*.sql.gz` 實際是「純 SQL 文字」(未必有壓縮)。還原指令下面已相容兩種情況。

## 手動立刻備份一次
```bash
docker exec hexagram-db-backup /backup.sh
```

## 還原(restore)
備份的 dump 帶 `--clean --if-exists`,還原會先清掉同名物件再重建。

**還原到正式庫(會覆蓋現有資料,請謹慎):**
```bash
cd /opt/hexagram
F=backups/daily/hexagram-latest.sql.gz
(gunzip -c "$F" 2>/dev/null || cat "$F") | docker exec -i postgres psql -U postgres -d hexagram
```

**先還原到臨時庫驗證(建議,安全):**
```bash
docker exec postgres psql -U postgres -c "CREATE DATABASE hexagram_restore_test;"
F=backups/daily/hexagram-latest.sql.gz
(gunzip -c "$F" 2>/dev/null || cat "$F") | docker exec -i postgres psql -U postgres -d hexagram_restore_test
docker exec postgres psql -U postgres -d hexagram_restore_test -tAc "SELECT count(*) FROM users;"
docker exec postgres psql -U postgres -c "DROP DATABASE hexagram_restore_test;"
```

## ⚠️ 還沒做:異地備份(上線前建議)
目前備份只在「同一台主機」,主機整台掛掉/被刪就沒了。上線前建議把 `./backups/`
再同步到**異地**(物件儲存),例如用 rclone/aws-cli 排程上傳到:
- Cloudflare R2 / Backblaze B2(便宜)、AWS S3、或另一台機器。
需要時再接(要你提供儲存桶與金鑰)。
