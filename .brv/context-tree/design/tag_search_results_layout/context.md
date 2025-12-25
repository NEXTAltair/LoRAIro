
Results filter bar now uses a separate format dropdown (結果フォーマット) while search conditions keep their own format/type/language/usage controls. Display filtering uses result format combo and excludes rows without that format; filter bar height fixed to combo size.

---

def _setup_results_filter_bar(self) -> None:
    filter_bar = QWidget(self.tabList)
    layout = QHBoxLayout(filter_bar)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    self._result_format_label = QLabel(self.tr("結果フォーマット:"), filter_bar)
    self._result_format_combo = QComboBox(filter_bar)
    self._result_format_combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToContents
    )
    self._result_format_combo.setMinimumWidth(140)

    layout.addWidget(self._result_format_label)
    layout.addWidget(self._result_format_combo)
    layout.addStretch(1)

    filter_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    filter_bar.setFixedHeight(self._result_format_combo.sizeHint().height() + 6)
    self.verticalLayout.insertWidget(0, filter_bar)

---

def _apply_display_filters(self, *args) -> None:
    if self._raw_df is None:
        return
    if self._result_format_combo is None:
        return
    format_name = normalize_choice(self._result_format_combo.currentText())
    format_key = format_name.strip().lower() if format_name else None

    rows = []
    for row in self._raw_df.iter_rows(named=True):
        format_statuses = row.get("format_statuses") or {}
        normalized_statuses = {
            str(key).strip().lower(): value for key, value in format_statuses.items()
        }
        if format_key and format_key not in normalized_statuses:
            continue
