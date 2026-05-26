# Ubuntu 小主機部署指南

## 一、把整個資料夾搬到 Ubuntu 主機

把這整個 `命卦排盤/` 資料夾（含所有檔案）複製到你的 Ubuntu 主機，例如：

```bash
# 假設你要放在 /home/你的帳號/hexagram 底下
scp -r 命卦排盤 你的帳號@主機IP:~/hexagram
# 或用 rsync / U 隨身碟 / git clone 都行
```

放好後 SSH 進主機：

```bash
cd ~/hexagram
ls
# 應該能看到 Dockerfile, docker-compose.yml, app.py ... 等檔案
```

## 二、啟動服務（推薦：使用 docker compose）

```bash
docker compose up -d
```

這一行會：
1. 自動 build 映像（第一次約 1-2 分鐘）
2. 背景啟動容器
3. 把主機 8080 port 對應到容器
4. 容器當掉會自動重啟
5. 主機重開機後也會自動啟動（`restart: unless-stopped`）

啟動完後，用瀏覽器打開：

```
http://你的主機IP:8080
```

例如主機 IP 是 `192.168.1.100`，就打 `http://192.168.1.100:8080`。
在主機本機上測試可以用 `http://localhost:8080`。

## 三、常用操作

| 動作 | 指令 |
|---|---|
| 查看狀態 | `docker compose ps` |
| 查看日誌 | `docker compose logs -f` |
| 重啟服務 | `docker compose restart` |
| 停止服務 | `docker compose down` |
| 改程式後重新部署 | `docker compose up -d --build` |
| 進容器看看 | `docker compose exec hexagram sh` |

## 四、改 port

如果 8080 有衝突，或想改成其他 port（例如 9000），編輯 `docker-compose.yml`：

```yaml
ports:
  - "9000:8080"   # 左邊是主機 port；右邊是容器內 port，維持 8080 不要動
```

改完後：

```bash
docker compose up -d
```

## 五、改成 80 port（免寫 port）

如果想直接用 `http://主機IP` 訪問（不用加 `:8080`）：

```yaml
ports:
  - "80:8080"
```

但 80 port 在 Linux 是特權 port，通常由 root 管理的 docker daemon 可以直接綁，正常執行 `docker compose up -d` 就行。
如果被其他服務佔用（例如 Apache/Nginx），會啟動失敗，需要先停掉那個服務。

## 六、移植 / 備份

整個 `命卦排盤/` 資料夾就是「專案全部」，要搬到另一台機器只需：
1. 把資料夾複製過去
2. 在新主機上 `docker compose up -d`

不需要搬 Docker image 本身（compose 會自動 build）。

## 七、常見問題

**Q：瀏覽器打不開，顯示「連線被拒絕」**
- 先確認容器有在跑：`docker compose ps`，`STATE` 應該是 `Up`
- 確認防火牆沒擋：`sudo ufw status`，必要時 `sudo ufw allow 8080`
- 用 `curl http://localhost:8080` 在主機上先測，能通再測從外部連

**Q：日干支時間不對**
- 容器已設為 `Asia/Taipei` 時區，但取決於主機時間是否正確
- 在主機上執行 `date`，確認主機時間正確
- 不正確的話：`sudo timedatectl set-timezone Asia/Taipei`

**Q：怎麼讓外網也能訪問**
- 需要在路由器做 port forwarding，把公網 port 轉到主機的 8080
- 強烈建議搭配 Cloudflare Tunnel、Tailscale，或加反向代理（Nginx/Caddy + Let's Encrypt）
- 直接把主機暴露在公網有安全風險，沒加 HTTPS 也不建議
