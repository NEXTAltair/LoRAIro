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

# stdin からのJSON入力をキャプチャ
HOOK_DATA=$(cat)
echo "STDIN data: $HOOK_DATA" >> "$LOG_FILE"

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

if [ -z "$ORIGINAL_COMMAND" ] || [ "$ORIGINAL_COMMAND" = "null" ]; then
    echo "No command found in HOOK_DATA" >> "$LOG_FILE"
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

# =========================== rg/git grep特別処理 ===========================
echo "Checking for rg/git grep commands: $COMMAND" >> "$LOG_FILE"

# rgコマンド → 段階的検索ガイダンス
if echo "$COMMAND" | grep -qE "^rg\s"; then
    echo "RG command detected, calling read_mcp_memorys.py" >> "$LOG_FILE"
    echo "$HOOK_DATA" | python3 /workspaces/LoRAIro/.claude/hooks/read_mcp_memorys.py
    RG_EXIT_CODE=$?
    echo "RG script exit code: $RG_EXIT_CODE" >> "$LOG_FILE"
    exit $RG_EXIT_CODE
fi

# git grepコマンド → フラグチェック
if echo "$COMMAND" | grep -qE "^git\s+grep"; then
    echo "Git grep command detected, calling bash_grep_checker.py" >> "$LOG_FILE"
    echo "$HOOK_DATA" | python3 /workspaces/LoRAIro/.claude/hooks/bash_grep_checker.py
    GREP_EXIT_CODE=$?
    echo "Git grep script exit code: $GREP_EXIT_CODE" >> "$LOG_FILE"
    exit $GREP_EXIT_CODE
fi
# =========================== rg/git grep特別処理終了 ========================

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
                    echo "Debug: FILES='$FILES'" >> "$LOG_FILE"
                    if [ -n "$FILES" ]; then
                        ACTUAL_HOOK=$(echo "$PRE_HOOK" | sed "s|\$FILES|$FILES|g")
                    else
                        echo "Debug: No Python files found, skipping auto-format" >> "$LOG_FILE"
                        continue  # Python ファイルがない場合はスキップ
                    fi
                else
                    ACTUAL_HOOK="$PRE_HOOK"
                fi

                echo "Debug: ACTUAL_HOOK='$ACTUAL_HOOK'" >> "$LOG_FILE"
                echo "実行コマンド: $ACTUAL_HOOK"
                eval "$ACTUAL_HOOK"

                if [ $? -eq 0 ]; then
                    echo "✅ 自動フォーマット完了"
                else
                    echo "⚠️ 自動フォーマット失敗 - 続行します"
                    # exit 1 を削除してコマンド実行を続行
                fi
            fi
        fi
    done <<< "$FORMAT_RULES"
fi

exit 0
