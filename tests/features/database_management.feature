# tests/features/database_management.feature
Feature: 画像データベース管理機能
  画像メタデータ、アノテーション、モデル情報を管理するための機能

  Background:
    Given データベースが初期化されている
    And モデルが登録されている

  Scenario: オリジナル画像の登録
    Given テスト用の画像ファイル "file01.webp" が存在する
    When 画像を登録する
    Then 画像メタデータがデータベースに保存される
    And 画像のUUIDが生成される
    And 画像のpHashが計算され保存される
    And manual_rating は NULL である

  Scenario: 処理済み画像の登録
    Given オリジナル画像が登録されている
    When 処理済み画像を登録する
    Then 処理済み画像のメタデータがデータベースに保存される
    And オリジナル画像と処理済み画像が関連付けられる

  Scenario: アノテーションの保存と取得
    Given オリジナル画像が登録されている
    When 以下のアノテーションを保存する:
      | type    | content          | model_id | confidence_score | is_edited_manually | existing |
      | tag     | person           | 1        | 0.9              | false              | false    |
      | tag     | outdoor          | 1        | 0.8              | false              | true     |
      | caption | a person outside | 1        |                  | false              | false    |
      | score   | 0.95             | 2        |                  | true               |          |
    Then アノテーションがデータベースに保存される
    And 保存したアノテーションを取得できる
    And 取得したタグ "person" (モデルID: 1) の is_edited_manually は false である
    And 取得したタグ "person" (モデルID: 1) の existing は false である
    And 取得したタグ "outdoor" (モデルID: 1) の existing は true である
    And 取得したキャプション "a person outside" (モデルID: 1) の is_edited_manually は false である
    And 取得したスコア 0.95 (モデルID: 2) の is_edited_manually は true である

  Scenario: タグによる詳細検索
    Given 以下の画像とアノテーションが登録されている:
      | image_file       | tags                    | caption                      |
      | file01.webp      | person, outdoor, sunny  | a person walking in the park |
      | file02.webp      | person, indoor         | person sitting indoor        |
      | file03.webp      | cat, outdoor           | cat sleeping outdoor         |
    When タグ "person, outdoor" AND で画像を検索する
    Then 1件の画像が返される
    When タグ "person, outdoor" OR で画像を検索する
    Then 3件の画像が返される

  Scenario: キャプションによる詳細検索
    Given 以下の画像とアノテーションが登録されている:
      | image_file       | tags                    | caption                      |
      | file01.webp      | person, outdoor, sunny  | a person walking in the park |
      | file02.webp      | person, indoor         | person sitting indoor        |
      | file03.webp      | cat, outdoor           | cat sleeping outdoor         |
    When キャプション person で部分一致検索する
    Then 2件の画像が返される

  Scenario: タグとキャプションの複合検索
    Given 以下の画像とアノテーションが登録されている:
      | image_file       | tags                    | caption                             |
      | file01.webp      | person, outdoor, sunny  | a person walking outdoor in the park |
      | file02.webp      | person, indoor         | person sitting indoor               |
      | file03.webp      | cat, outdoor           | cat sleeping outdoor                |
    When タグ person AND キャプション outdoor で検索する
    Then 1件の画像が返される

  Scenario: 日付範囲による検索
    Given 以下の画像とアノテーションが登録されている:
      | image_file       | tags           | caption       | registration_offset_days |
      | file01.webp      | recent         | recent entry  | 0                        |
      | file02.webp      | one_day_ago    | old entry     | 1                        |
      | file03.webp      | two_days_ago   | very old entry| 2                        |
    When 過去24時間以内のアノテーションで検索する
    Then 1件の画像が返される
    When 特定の日付範囲 ("-2 days", "-0.5 days") で検索する
    Then 1件の画像が返される

  Scenario: NSFWコンテンツの除外検索
    Given 以下の画像とアノテーションが登録されている:
      | image_file       | tags           | caption       |
      | file01.webp      | safe           | safe image    |
      | file02.webp      | nsfw, explicit | nsfw image    |
      | file03.webp      | safe, person   | another safe  |
    When include_nsfw=False で検索する
    Then 2件の画像が返される

  Scenario: 手動編集フラグによるフィルタリング
    Given 以下の画像とアノテーションが登録されている:
      | image_file       | tags           | caption       | score | manual_edit_target |
      | file01.webp      | person, safe   | safe image 1  | 0.8   | tag:person         |
      | file02.webp      | animal, safe   | safe image 2  | 0.7   | caption            |
      | file03.webp      | object, safe   | safe image 3  | 0.9   | score              |
      | file04.webp      | landscape, safe| safe image 4  | 0.6   | none               |
    When is_edited_manually=true でフィルタリングする
    Then 3件の画像が返される
    When is_edited_manually=false でフィルタリングする
    Then 1件の画像が返される

  Scenario: 手動レーティングによるフィルタリング
    Given 以下の画像とアノテーションが登録されている:
      | image_file       | tags           | caption       | manual_rating |
      | file01.webp      | person, safe   | safe image 1  | PG            |
      | file02.webp      | animal, safe   | safe image 2  | R             |
      | file03.webp      | object, safe   | safe image 3  | PG            |
      | file04.webp      | landscape, safe| safe image 4  |               |
    When manual_rating="PG" でフィルタリングする
    Then 2件の画像が返される
    When manual_rating="R" でフィルタリングする
    Then 1件の画像が返される
    When manual_rating="X" でフィルタリングする
    Then 0件の画像が返される