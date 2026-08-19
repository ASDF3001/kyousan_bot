# 設定と環境変数ガイド (Setting Info)

Kyousanshumi Bot の動作をカスタマイズするための環境変数（`.env`）および `/setting` コマンドの使い方についてまとめました。

## 環境変数 (`.env`)

Botのルートディレクトリにある `.env` ファイルで各種設定を指定できます。
値が指定されていない場合は一部の機能がオフになったり、動作に影響が出たりします。

| 変数名 | 必須 | 内容 | 例 |
|---|---|---|---|
| `DISCORD_TOKEN` | **必須** | Discord Botのアクセストークン | `MTEy...` |
| `RANKING_CHANNEL_ID` | 任意 | 金曜20時の週間ランキングの自動投稿先チャンネルID | `123456789012345678` |
| `DEFAULT_RACE_CHANNEL_ID` | 任意 | デフォルトのあけおめ受付チャンネルID（`/setting set_race_channel` で上書き可能） | `123456789012345678` |
| `AKEOME_STAMP_ID` | 任意 | あけおめ判定に使うカスタム絵文字のID | `1515228180343160943` |
| `LOGIN_NOTIFY_CHANNEL_ID` | 任意 | デイリーログインボーナスの通知を固定で送信するチャンネルのID。未指定時は「発言したチャンネル」に直接通知されます | `123456789012345678` |
| `ALLOWED_ROLES` | 任意 | `/censor` 等の管理コマンドを使用できるロールID（カンマ区切りで複数指定可） | `111,222,333` |

---

## データベース内の設定 (`/setting` コマンド)

Discord上で `/setting` コマンドを使用することで、ボットを再起動せずに動的に設定を変更できます。
これらの設定は `kyosan_bot.db` の `bot_config` や `scan_targets` テーブルに保存されます。

### スレッド自動走査設定
3日に1回、深夜4時にBotが特定チャンネル（テキストチャンネル・フォーラムチャンネル）のスレッド履歴を自動取得（走査）します。
これを利用するには、事前に走査対象チャンネルを登録する必要があります。

- `/setting action:add_target channel:#対象チャンネル`
  - 走査対象チャンネルをリストに追加します。
- `/setting action:remove_target channel:#対象チャンネル`
  - 走査対象チャンネルから除外します。
- `/setting action:toggle_notify channel:#対象チャンネル`
  - そのチャンネルの走査開始・完了時の通知をON/OFFします。
- `/setting action:list_targets`
  - 現在の走査対象と、あけおめ受付チャンネルの一覧を表示します。

### あけおめ競争の設定
あけおめメッセージを受け付けるチャンネルを変更できます。
- `/setting action:set_race_channel channel:#チャンネル`
  - 指定したチャンネルをあけおめ受付チャンネルとしてDBに保存します。（環境変数の `DEFAULT_RACE_CHANNEL_ID` よりも優先されます）
