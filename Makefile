#!make

help: _header
	${info }
	@echo Opciones:
	@echo -----------------------
	@echo crear
	@echo actualizar
	@echo guardar
	@echo -----------------------

_header:
	@echo -----------------
	@echo Debian OpenNebula
	@echo -----------------

crear:
	@poetry run python crear.py

actualizar:
	@ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_FORCE_COLOR=True ansible-playbook -i hosts.ini -u root actualizar.yml

guardar:
	@poetry run python guardar.py
