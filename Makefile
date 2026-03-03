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

debian:
	@poetry run python debian.py
