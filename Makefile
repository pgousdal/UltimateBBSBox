.PHONY: check schema registry test ansible-syntax

check: schema registry test ansible-syntax

schema:
	python3 scripts/ubb-schema.py

registry:
	python3 scripts/ubb-registry.py validate

test:
	python3 -m unittest discover -s tests -v

ansible-syntax:
	@if command -v ansible-playbook >/dev/null 2>&1; then \
		ansible-playbook --syntax-check playbooks/site.yml; \
		ansible-playbook --syntax-check playbooks/bootstrap.yml; \
	else \
		echo "SKIP ansible syntax: ansible-playbook not installed"; \
	fi
