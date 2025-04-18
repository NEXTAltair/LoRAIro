# AIアノテーション Application層計画書

## 1. 目的
- 画像アノテーションの非同期実行・DB保存・進捗/エラー通知などサービス層の責務を明確化する。

## 2. 設計方針
- 非同期処理・進捗通知の標準化
- DB保存・データ整形の一元化
- エラー処理・ロギングの徹底
- Application層とcore層・interface層の明確な分離

## 3. マイルストーン
- [ ] サービスクラス設計・API仕様の確定
- [ ] 非同期処理・進捗通知方式の決定
- [ ] DB保存・データ整形ロジックの実装
- [ ] エラー・例外設計のレビュー
- [ ] テスト・ドキュメント整備

## 4. 参考
- image-annotator-lib: api.py, core/base.py
- lorairo: services/annotation_service.py, database/db_manager.py

---

（本ドキュメントはApplication層観点のAIアノテーションサービス計画書です） 