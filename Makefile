#!make

help: _header
	${info }
	@echo Opciones:
	@echo -----------------------
	@echo debian
	@echo -----------------------

_header:
	@echo -----------------
	@echo Debian OpenNebula
	@echo -----------------

ocr:
	@poetry run python debian.py
