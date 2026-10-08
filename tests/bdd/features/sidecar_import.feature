Feature: 異常な付属テキストをスキップして画像登録を続ける
  付属テキストは通常ファイルかつ1ファイル1MiB以内に限定する。
  片方が上限を超えても正常なもう片方と画像本体、後続画像を登録する。

  Scenario Outline: GUIと共通登録入口で正常な兄弟ファイルと後続画像を保存する
    Given 異常な "<suffix>" と正常なもう片方の付属ファイルを持つ画像がある
    And 正常な付属テキストを持つ後続画像がある
    When "<entry>" 経路で画像を登録する
    Then 画像2枚と正常な付属テキストのみがDBに保存される

    Examples:
      | suffix   | entry  |
      | .txt     | worker |
      | .caption | worker |
      | .txt     | common |
      | .caption | common |
