.PHONY: check check-strict schema registry test ansible-syntax ansible-syntax-strict

check: schema registry test ansible-syntax
	@echo "=== Validation Summary ==="
	@echo "Python tests        PASS"
	@echo "Catalog/schema      PASS"
	@echo "Downloader guard    PASS (covered by integration tests)"
	@if command -v ansible-playbook >/dev/null 2>&1; then echo "Ansible syntax      PASS"; else echo "Ansible syntax      SKIP: ansible-playbook unavailable"; fi
	@if command -v ansible-playbook >/dev/null 2>&1; then echo "Overall             PASS"; else echo "Overall             PASS WITH SKIPS"; fi

check-strict: schema registry test ansible-syntax-strict
	@echo "=== Validation Summary ==="
	@echo "Overall             PASS"

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
		echo "SKIP ansible syntax: dependency unavailable (ansible-playbook missing)"; \
	fi

ansible-syntax-strict:
	@if ! command -v ansible-playbook >/dev/null 2>&1; then \
		echo "FAIL ansible syntax: required tooling unavailable"; exit 2; \
	fi
	@ansible-playbook --syntax-check playbooks/site.yml
	@ansible-playbook --syntax-check playbooks/bootstrap.yml
