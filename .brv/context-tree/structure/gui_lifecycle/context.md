
showEvent init assumes services are set; no DB init or heavy work in UI.

---

closeEvent: service close -> DB close -> super().closeEvent, continue on exceptions.
