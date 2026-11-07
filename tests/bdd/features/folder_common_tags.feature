Feature: ディレクトリ取り込み時にサブフォルダごとの共通タグを付ける
  サブフォルダごとに入力した共通タグは、そのサブフォルダ直下の全画像に手動タグとして付く。
  タグ DB の入力規則には合わせず、入力した表記のまま保存する。

  Scenario: 入力した共通タグがそのサブフォルダの画像だけに付く
    Given サブフォルダ "chara_a" に画像が2枚、"chara_b" に画像が1枚、選択ディレクトリ直下に画像が1枚ある
    And サブフォルダ "chara_a" の共通タグに "Chara A, blue sky" を入力する
    When ディレクトリを取り込む
    Then "chara_a" の画像2枚に手動タグ "Chara A" と "blue sky" が tag_id なしで付く
    And "chara_b" の画像と選択ディレクトリ直下の画像には共通タグが付かない
    And タグ DB への解決や登録は行われない

  Scenario: 既に同じタグを持つ画像には重複して付けない
    Given サブフォルダ "chara_a" に付属テキスト "blue sky" を持つ画像が1枚ある
    And サブフォルダ "chara_a" の共通タグに "blue sky, smile" を入力する
    When ディレクトリを取り込む
    And 同じディレクトリを同じ共通タグで再度取り込む
    Then "chara_a" の画像には "blue sky" と "smile" が1件ずつだけある
