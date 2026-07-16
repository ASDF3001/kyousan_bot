# Kyousanshumi（共産趣味ボット）

Discord サーバー「共産趣味」向けの活動実績bot。メッセージ数の集計・ランキング表示・あけおめ最速競争などを行う。

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env   # 実トークンを貼る
python3 main.py
```

## 設定（環境変数）

| 変数 | 内容 |
|------|------|
| `DISCORD_TOKEN` | Discord Bot トークン（必須） |

## コマンド一覧

| コマンド | 権限 | 説明 |
|----------|------|------|
| `/activity_ranking` | 全員 | ユーザー・スレッドの発言数ランキングを表示。`hide_user=True` でスレッドのみ |
| `/akeome_ranking` | 全員 | 今月のあけおめ最速ランキングを表示 |
| `/omikuji` | 全員 | 今日の運勢（党からの評価）を占う |
| `/stats` | 全員 | 自分の総発言数と全体順位を表示（自分のみ参照可） |
| `/censor` | 管理者/権限ロール | 指定ユーザーのメッセージを一括削除 |
| `/setting` | 管理者/権限ロール | 走査設定の管理（下記） |
| `/soviet_sync` | 管理者 | 全走査対象のログを手動で再集計 |

### `/setting` サブコマンド

| action | 引数 | 説明 |
|--------|------|------|
| `add_target` | `channel` | 走査対象チャンネルを追加 |
| `remove_target` | `channel` | 走査対象から削除 |
| `toggle_notify` | `channel` | そのチャンネルの走査通知 ON/OFF |
| `list_targets` | — | 現在の走査対象・あけおめ受付チャンネルを一覧 |
| `set_race_channel` | `channel` | あけおめ受付チャンネルを変更 |

## データベース構成（`kyosan_bot.db`）

| テーブル | 内容 |
|----------|------|
| `user_activity` | ユーザーごとの累計発言数 |
| `thread_activity` | スレッドごとの発言数 |
| `akeome_records` | あけおめ計測記録（user_id, date_str, response_ms, is_flying） |
| `scan_targets` | 走査対象チャンネル（channel_id, notify） |
| `bot_config` | 各種設定（race_channel など） |

## 自動タスク

- **0:00:30 JST** — 前日のあけおめ計測結果を race_channel へ投稿。0:00〜0:01 は進捗バーを表示。
- **0:00 / 金曜 20:00 JST** — 週間ランキングを RANKING_CHANNEL へ投稿（金曜のみ）。
- **4:00 JST（3日に1回）** — 全走査対象チャンネルのログを自動再集計。

## あけおめ最速競争のルール

- 受付チャンネルで `あけおめ` と投稿。
- **成功**: 当日 0:00:00 〜 0:01:00（JST）。即座に順位リアクション（1️⃣〜9️⃣ / 10位以降はテキスト）と自己ベストを返信。
- **フライング**: 前日 23:59:00 〜 23:59:59。翌日の集計で「シベリア行き」として表示。
- 該当日の 0:00:30 に結果をまとめて投稿。

## 注意

- トークンは `.env` にのみ格納。`.env` は `.gitignore` で除外済み。
- SQLite は WAL モード。DBファイル（`*.db*`）はコミットしない。
