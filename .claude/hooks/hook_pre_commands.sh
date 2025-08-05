#!/bin/bash

# LoRAIro Project - Pre-Command Hook
# ルールファイルベースの厳格なコマンド変換・チェックスクリプト

# =========================== デバッグコード開始 ===========================
# ログディレクトリを確実に作成
LOG_DIR="/workspaces/LoRAIro/.claude/logs"
LOG_FILE="$LOG_DIR/hook_pre_commands_debug.log"
mkdir -p "$LOG_DIR"

echo "=== Hook Debug $(date) ===" >> "$LOG_FILE"
echo "Hook executed with args: $@" >> "$LOG_FILE"
echo "HOOK_DATA variable: $HOOK_DATA" >> "$LOG_FILE"

# stdin からの入力をキャプチャ
if [ -p /dev/stdin ]; then
    STDIN_DATA=$(cat)
    echo "STDIN data: $STDIN_DATA" >> "$LOG_FILE"
    # 後続処理で使うためにHOOK_DATAに代入
    HOOK_DATA="$STDIN_DATA"
else
    HOOK_DATA="${1:-}"
fi

echo "Final HOOK_DATA: $HOOK_DATA" >> "$LOG_FILE"
echo "=================================" >> "$LOG_FILE"
# =========================== デバッグコード終了 ===============

RULES_FILE="$(dirname "$0")/rules/hook_pre_commands_rules.json"

# jqが利用可能かチェック
if ! command -v jq &> /dev/null; then
    echo "Warning: jq is not installed. Skipping pre-command checks."
    exit 0
fi

# 入力データからコマンドを取得
ORIGINAL_COMMAND=$(echo "$HOOK_DATA" | jq -r '.tool_input.command // empty' 2>/dev/null)

if [ -z "$ORIGINAL_COMMAND" ]; then
    exit 0
fi

echo "Original command: $ORIGINAL_COMMAND" >> "$LOG_FILE"

# LoRAIro環境コマンド変換関数(ルールファイルベース)
transform_lorairo_command() {
    local cmd="$1"

    # ルールファイルが存在する場合のみ変換処理
    if [ -f "$RULES_FILE" ]; then
        # lorairo_environment_transforms セクションから変換ルールを読み込み
        TRANSFORMS=$(jq -c '.lorairo_environment_transforms[]?' "$RULES_FILE" 2>/dev/null)
        while IFS= read -r transform; do
            if [ -n "$transform" ]; then
                PATTERN=$(echo "$transform" | jq -r '.pattern')
                TRANSFORM_CMD=$(echo "$transform" | jq -r '.transform')
                DESCRIPTION=$(echo "$transform" | jq -r '.description')

                echo "Checking pattern: $PATTERN against: $cmd" >> /tmp/hook_debug.log

                if echo "$cmd" | grep -qE "$PATTERN"; then
                    # sed変換を適用
                    CONVERTED=$(echo "$cmd" | sed "$TRANSFORM_CMD")
                    echo "Transform applied: $TRANSFORM_CMD -> $CONVERTED" >> /tmp/hook_debug.log
                    echo "$CONVERTED"
                    return
                fi
            fi
        done <<< "$TRANSFORMS"
    fi

    # 変換対象外の場合は元のコマンドをそのまま返す
    echo "$cmd"
}

# LoRAIro環境コマンド変換を適用
COMMAND=$(transform_lorairo_command "$ORIGINAL_COMMAND")

echo "Transformed command: $COMMAND" >> /tmp/hook_debug.log

# 変換が適用された場合はClaude Codeにブロック+提案を返す
if [ "$COMMAND" != "$ORIGINAL_COMMAND" ]; then
    cat << EOF
{
    "decision": "block",
    "reason": "🔄 LoRAIro環境コマンドに自動変換: $COMMAND\n\n元コマンド: $ORIGINAL_COMMAND\n変換後: $COMMAND"
}
EOF
    exit 2  # ツールコールをブロックして変換後コマンドを提案
fi

# ルールファイルが存在する場合のみルールチェック実行
if [ -f "$RULES_FILE" ]; then
    echo "🔍 Command check: $COMMAND"

    # 1. ドキュメント優先チェック
    DOC_FIRST_RULES=$(jq -c '.documentation_first_commands[]?' "$RULES_FILE" 2>/dev/null)
    while IFS= read -r rule; do
        if [ -n "$rule" ]; then
            PATTERN=$(echo "$rule" | jq -r '.pattern')
            REASON=$(echo "$rule" | jq -r '.reason')
            SUGGESTION=$(echo "$rule" | jq -r '.suggestion')

            if echo "$COMMAND" | grep -qE "$PATTERN"; then
                echo "📚 ドキュメント優先推奨:"
                echo "理由: $REASON"
                echo "提案: $SUGGESTION"
                echo ""
            fi
        fi
    done <<< "$DOC_FIRST_RULES"

    # 1.5. ライブラリ調査提案チェック
    LIB_INVESTIGATION_RULES=$(jq -c '.library_investigation_suggestions[]?' "$RULES_FILE" 2>/dev/null)
    while IFS= read -r rule; do
        if [ -n "$rule" ]; then
            PATTERN=$(echo "$rule" | jq -r '.pattern')
            REASON=$(echo "$rule" | jq -r '.reason')
            SUGGESTION=$(echo "$rule" | jq -r '.suggestion')

            if echo "$COMMAND" | grep -qE "$PATTERN"; then
                echo "🔬 ライブラリ調査推奨:"
                echo "理由: $REASON"
                echo "提案: $SUGGESTION"
                echo ""
            fi
        fi
    done <<< "$LIB_INVESTIGATION_RULES"

    # 2. ブロックコマンドチェック
    BLOCKED_RULES=$(jq -c '.blocked_commands[]?' "$RULES_FILE" 2>/dev/null)
    while IFS= read -r rule; do
        if [ -n "$rule" ]; then
            PATTERN=$(echo "$rule" | jq -r '.pattern')
            REASON=$(echo "$rule" | jq -r '.reason')
            SUGGESTION=$(echo "$rule" | jq -r '.suggestion')

            if echo "$COMMAND" | grep -qE "$PATTERN"; then
                cat << EOF
{
    "decision": "block",
    "reason": "🚫 コマンドがブロックされました:\n理由: $REASON\n代替案: $SUGGESTION"
}
EOF
                exit 2
            fi
        fi
    done <<< "$BLOCKED_RULES"

    # 3. 自動フォーマットチェック
    FORMAT_RULES=$(jq -c '.auto_format_commands[]?' "$RULES_FILE" 2>/dev/null)
    while IFS= read -r rule; do
        if [ -n "$rule" ]; then
            PATTERN=$(echo "$rule" | jq -r '.pattern')
            PRE_HOOK=$(echo "$rule" | jq -r '.pre_hook')
            DESCRIPTION=$(echo "$rule" | jq -r '.description')

            if echo "$COMMAND" | grep -qE "$PATTERN"; then
                echo "🛠️ 自動フォーマット実行: $DESCRIPTION"

                # $FILESを実際のファイルリストで置換 (git addの場合)
                if echo "$COMMAND" | grep -q "^git add"; then
                    FILES=$(echo "$COMMAND" | sed 's/git add //' | tr ' ' '\n' | grep '\.py$' | tr '\n' ' ')
                    ACTUAL_HOOK=$(echo "$PRE_HOOK" | sed "s/\$FILES/$FILES/g")
                else
                    ACTUAL_HOOK="$PRE_HOOK"
                fi

                echo "実行コマンド: $ACTUAL_HOOK"
                eval "$ACTUAL_HOOK"

                if [ $? -eq 0 ]; then
                    echo "✅ 自動フォーマット完了"
                else
                    echo "❌ 自動フォーマット失敗"
                    exit 1
                fi
            fi
        fi
    done <<< "$FORMAT_RULES"
fi

exit 0
