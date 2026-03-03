#!make

help: _header
	${info }
	@echo Opciones:
	@echo -----------------------
	@echo debian
	@echo actualizar
	@echo -----------------------

_header:
	@echo -----------------
	@echo Debian OpenNebula
	@echo -----------------

debian:
	@poetry run python debian.py

actualizar:
	@ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_FORCE_COLOR=True ansible-playbook -i hosts.ini -u root actualizar.yml
