"""Domain specifications. DOMAINS maps name -> Domain."""

from jevbench.datagen.domains import (agent_logs, content_moderation, customer_support, ecommerce_returns,
                                      education_grading, finance_ops, healthcare_admin, hr_recruiting,
                                      it_incidents, legal_contracts, logistics, security_ops)

DOMAINS = {d.name: d for d in (customer_support.DOMAIN, security_ops.DOMAIN, content_moderation.DOMAIN,
                               finance_ops.DOMAIN, it_incidents.DOMAIN, ecommerce_returns.DOMAIN,
                               hr_recruiting.DOMAIN, healthcare_admin.DOMAIN, legal_contracts.DOMAIN,
                               logistics.DOMAIN, education_grading.DOMAIN, agent_logs.DOMAIN)}
