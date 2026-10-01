# Balance report: frozen

Source: synthetic, fact-first (JevBench datagen)

240 cases kept from 375 plans; {'customer_support': 20, 'content_moderation': 20, 'finance_ops': 20, 'security_ops': 20, 'it_incidents': 20, 'ecommerce_returns': 20, 'hr_recruiting': 20, 'healthcare_admin': 20, 'legal_contracts': 20, 'logistics': 20, 'education_grading': 20, 'agent_logs': 20} per domain.

Rejected plans: length out of band 16, surplus (domain already full) 119.
Token check: skipped (tokenizer not cached).

| Dimension | Counts |
|---|---|
| archetype | {'outage': 10, 'how_to': 4, 'billing_dispute': 4, 'cancellation': 6, 'spam': 5, 'no_violation': 5, 'misinformation': 5, 'harassment': 5, 'possible_duplicate': 4, 'bank_detail_change': 6, 'expense_claim': 6, 'invoice_approval': 4, 'exfiltration': 5, 'malware': 5, 'phishing': 5, 'brute_force': 5, 'access_request': 5, 'hardware': 6, 'performance': 5, 'wrong_item': 6, 'not_delivered': 5, 'changed_mind': 5, 'damaged_item': 4, 'offer_counter': 5, 'interview_feedback': 5, 'application': 5, 'internal_transfer': 5, 'claim_denied': 5, 'appointment_request': 5, 'billing_question': 5, 'records_request': 5, 'nda_review': 5, 'breach_claim': 5, 'renewal': 5, 'vendor_contract': 5, 'delayed': 5, 'address_issue': 5, 'damaged': 5, 'customs_hold': 5, 'late_submission': 4, 'extension_request': 5, 'grade_appeal': 5, 'plagiarism_flag': 6, 'completed': 5, 'permission_denied': 6, 'destructive_action': 4, 'tool_error': 5} |
| style | {'customer email': 6, 'support ticket form': 5, 'short mobile message': 3, 'live chat transcript': 11, 'moderation queue entry': 5, 'user report form': 5, 'moderator handoff note': 6, 'trust and safety chat message': 4, 'accounts payable ticket': 5, 'email to the finance team': 6, 'ERP exception report': 5, 'finance team chat message': 4, 'SIEM alert summary': 5, 'employee report email': 6, 'analyst shift note': 4, 'chat message to the security channel': 5, 'service desk ticket': 6, 'email to IT support': 5, 'on-call chat message': 4, 'monitoring alert with notes': 5, 'customer email to the shop': 5, 'return request form': 4, 'order support ticket': 6, 'applicant tracking system note': 5, 'email to the HR team': 5, 'hiring manager message': 5, 'HR case summary': 5, 'front desk call note': 5, 'billing office email': 6, 'insurance correspondence summary': 4, 'patient portal message': 5, 'legal intake form': 5, 'email to the legal team': 5, 'contract review request': 5, 'legal team chat message': 5, 'shipment exception report': 6, 'driver or agent note': 5, 'operations chat message': 6, 'email from the customer': 3, 'student email to the course office': 5, 'learning platform case note': 6, "marker's note": 5, 'course office chat message': 4, 'agent run log excerpt': 5, 'run summary written by the agent': 5, "reviewer's note on a run": 6, 'incident message from an operator': 4} |
| length | {'80-150': 85, '250-350': 76, '150-250': 79} |
| mention | {'explicit': 1244, 'implied': 87, 'absent': 273} |
| question_types | {'noul': 1341, 'choice': 615, 'score': 284} |

Questions whose answer is fixed by the scenario type (for example feature_failing, incident_type) follow the archetype balance, not an even answer split.

| Question | Gold answers | Correct option position (Choice) |
|---|---|---|
| account_risk | {'0': 2, '1': 2, '2': 2, '3': 2, 'unknown': 2} |  |
| action | {'accept': 4, 'approve': 7, 'ask_for_documents': 5, 'contact_recipient': 5, 'escalate': 15, 'file_claim': 2, 'fulfil': 5, 'hold': 4, 'keep': 5, 'label': 3, 'negotiate': 6, 'penalise': 5, 'proceed': 4, 'refuse': 7, 'reject': 5, 'remove': 6, 'reship': 3, 'review': 4, 'roll_back': 2, 'send_notice': 4, 'suspend': 4, 'unknown': 24, 'wait': 6, 'wait_for_approval': 5} | {0: 30, 1: 30, 2: 27, 3: 29} |
| admin_account | {'False': 8, 'True': 8, 'unknown': 4} |  |
| admin_rights | {'False': 2, 'True': 2, 'unknown': 1} |  |
| affected_system | {'VPN': 2, 'email': 2, 'internal wiki': 3, 'payroll system': 4, 'unknown': 3} | {0: 4, 1: 2, 2: 2, 3: 3} |
| already_hidden | {'False': 9, 'True': 6, 'unknown': 2} |  |
| any_overdue | {'False': 2, 'True': 2, 'unknown': 1} |  |
| approved | {'False': 2, 'True': 3} |  |
| asked_for_help | {'False': 5, 'True': 5, 'unknown': 1} |  |
| assessment_type | {'essay': 7, 'final exam': 2, 'lab report': 4, 'unknown': 4, 'weekly quiz': 3} | {0: 4, 1: 4, 2: 4, 3: 4} |
| attack_stage | {'exfiltration': 5, 'initial_access': 5, 'persistence': 3, 'recon': 3, 'unknown': 4} | {0: 4, 1: 4, 2: 4, 3: 4} |
| authorized | {'False': 2, 'True': 3} |  |
| big_dispute | {'False': 2, 'True': 3} |  |
| breach_admitted | {'False': 3, 'True': 2} |  |
| breaks_rule | {'False': 5, 'True': 12} |  |
| business_wants_out | {'False': 2, 'True': 3} |  |
| bypass_attempted | {'False': 2, 'True': 3, 'unknown': 1} |  |
| came_by_email | {'False': 3, 'True': 2, 'unknown': 1} |  |
| can_appeal | {'False': 2, 'True': 2, 'unknown': 1} |  |
| can_start_now | {'False': 6, 'True': 6, 'unknown': 3} |  |
| case_strength | {'0': 3, '1': 4, '2': 4, '3': 5, 'unknown': 4} |  |
| case_type | {'extension_request': 5, 'grade_appeal': 5, 'late_submission': 4, 'plagiarism_flag': 6} | {0: 5, 1: 6, 2: 5, 3: 4} |
| change_verified | {'False': 4, 'True': 1, 'unknown': 1} |  |
| churn_risk | {'0': 3, '1': 4, '2': 7, '3': 6} |  |
| close_together | {'False': 3, 'True': 1} |  |
| cold_chain | {'False': 3, 'True': 5, 'unknown': 2} |  |
| competitor_named | {'False': 7, 'True': 9} |  |
| concern_raised | {'False': 2, 'True': 2, 'unknown': 1} |  |
| config_changed | {'False': 3, 'True': 3} |  |
| confirmed_first | {'False': 1, 'True': 2, 'unknown': 1} |  |
| consent_attached | {'False': 2, 'True': 2, 'unknown': 1} |  |
| credentials_entered | {'False': 2, 'True': 2, 'unknown': 1} |  |
| customer_upset | {'False': 7, 'True': 11} |  |
| data_safe | {'False': 2, 'True': 3, 'unknown': 1} |  |
| deadline_close | {'False': 2, 'True': 2, 'unknown': 1} |  |
| deadline_given | {'False': 9, 'True': 10} |  |
| deadline_imminent | {'False': 2, 'True': 2, 'unknown': 1} |  |
| deadline_this_week | {'False': 2, 'True': 2, 'unknown': 1} |  |
| decision | {'decline': 5, 'deny': 5, 'escalate': 3, 'hold': 3, 'investigate': 3, 'proceed': 5, 'refund': 2, 'replace': 7, 'unknown': 7} | {0: 9, 1: 8, 2: 7, 3: 9} |
| documented_reason | {'False': 4, 'True': 3, 'unknown': 2} |  |
| due_this_week | {'False': 5, 'True': 7, 'unknown': 2} |  |
| duties_settled | {'False': 2, 'True': 2, 'unknown': 1} |  |
| earlier_case | {'False': 3, 'True': 2, 'unknown': 1} |  |
| enterprise_plan | {'False': 9, 'True': 7, 'unknown': 3} |  |
| exception_type | {'address_issue': 5, 'customs_hold': 5, 'damaged': 5, 'delayed': 5} | {0: 6, 1: 5, 2: 3, 3: 6} |
| expense_type | {'equipment': 1, 'meals': 1, 'software': 1, 'travel': 2, 'unknown': 1} | {0: 2, 1: 1, 2: 1, 3: 1} |
| expensive_run | {'False': 9, 'True': 7, 'unknown': 4} |  |
| exposure | {'0': 5, '1': 3, '2': 4, '3': 4, 'unknown': 4} |  |
| feature_failing | {'False': 14, 'True': 5} |  |
| file_quarantined | {'False': 2, 'True': 2, 'unknown': 1} |  |
| first_invoice | {'False': 3, 'True': 1} |  |
| fraud_risk | {'0': 5, '1': 4, '2': 6, '3': 1, 'unknown': 4} |  |
| frequent_returner | {'False': 8, 'True': 9, 'unknown': 3} |  |
| goods_received | {'False': 1, 'True': 3} |  |
| had_extension | {'False': 2, 'True': 2, 'unknown': 1} |  |
| handles_personal_data | {'False': 2, 'True': 2, 'unknown': 1} |  |
| has_insurance | {'False': 3, 'True': 5, 'unknown': 2} |  |
| high_similarity | {'False': 3, 'True': 3} |  |
| high_stakes | {'False': 7, 'True': 6, 'unknown': 2} |  |
| high_value | {'False': 9, 'True': 8, 'unknown': 3} |  |
| identity_checked | {'False': 3, 'True': 1, 'unknown': 1} |  |
| incident_type | {'brute_force': 5, 'exfiltration': 5, 'malware': 5, 'phishing': 5} | {0: 5, 1: 6, 2: 4, 3: 5} |
| info_missing | {'False': 2, 'True': 2, 'unknown': 1} |  |
| instalments_asked | {'False': 2, 'True': 3} |  |
| insured | {'False': 2, 'True': 2, 'unknown': 1} |  |
| is_essay | {'False': 9, 'True': 7, 'unknown': 4} |  |
| item_opened | {'False': 2, 'True': 2, 'unknown': 1} |  |
| item_type | {'application': 5, 'internal_transfer': 5, 'interview_feedback': 5, 'offer_counter': 5} | {0: 5, 1: 5, 2: 5, 3: 5} |
| key_account | {'False': 7, 'True': 9, 'unknown': 4} |  |
| large_account | {'False': 9, 'True': 8, 'unknown': 3} |  |
| large_amount | {'False': 13, 'True': 12, 'unknown': 5} |  |
| large_shipment | {'False': 8, 'True': 8, 'unknown': 4} |  |
| large_transfer | {'False': 2, 'True': 2, 'unknown': 1} |  |
| late_claim | {'False': 3, 'True': 2, 'unknown': 1} |  |
| law | {'California': 2, 'England': 2, 'New York': 2, 'Singapore': 2, 'unknown': 2} | {0: 2, 1: 2, 2: 2, 3: 2} |
| link_clicked | {'False': 2, 'True': 2, 'unknown': 1} |  |
| link_present | {'False': 5, 'True': 5} |  |
| login_succeeded | {'False': 2, 'True': 3} |  |
| long_disruption | {'False': 4, 'True': 4, 'unknown': 1} |  |
| long_notice | {'False': 7, 'True': 5, 'unknown': 3} |  |
| long_run | {'False': 8, 'True': 9, 'unknown': 3} |  |
| long_term | {'False': 4, 'True': 4, 'unknown': 2} |  |
| loyalty_member | {'False': 8, 'True': 9, 'unknown': 3} |  |
| manager_backs | {'False': 2, 'True': 2, 'unknown': 1} |  |
| many_files | {'False': 4, 'True': 3, 'unknown': 2} |  |
| many_reports | {'False': 7, 'True': 8, 'unknown': 3} |  |
| many_retries | {'False': 2, 'True': 2, 'unknown': 1} |  |
| many_sources | {'False': 4, 'True': 5, 'unknown': 1} |  |
| many_users | {'False': 4, 'True': 3, 'unknown': 2} |  |
| matter_type | {'breach_claim': 5, 'nda_review': 5, 'renewal': 5, 'vendor_contract': 5} | {0: 5, 1: 5, 2: 5, 3: 5} |
| may_leave | {'False': 8, 'True': 10} |  |
| mfa_enabled | {'False': 9, 'True': 8, 'unknown': 3} |  |
| mostly_damaged | {'False': 1, 'True': 3, 'unknown': 1} |  |
| mutual_nda | {'False': 2, 'True': 2, 'unknown': 1} |  |
| needed_soon | {'False': 3, 'True': 2} |  |
| needed_this_week | {'False': 2, 'True': 3} |  |
| needed_today | {'False': 6, 'True': 4, 'unknown': 1} |  |
| needs_manager | {'False': 2, 'True': 3, 'unknown': 1} |  |
| new_account | {'False': 7, 'True': 8, 'unknown': 3} |  |
| new_patient | {'False': 1, 'True': 3, 'unknown': 1} |  |
| notice_already_sent | {'False': 2, 'True': 2, 'unknown': 1} |  |
| old_breach | {'False': 2, 'True': 2, 'unknown': 1} |  |
| old_device | {'False': 2, 'True': 3, 'unknown': 1} |  |
| other_offer | {'False': 3, 'True': 2} |  |
| our_template | {'False': 4, 'True': 4, 'unknown': 2} |  |
| outcome_type | {'completed': 5, 'destructive_action': 4, 'permission_denied': 6, 'tool_error': 5} | {0: 5, 1: 5, 2: 6, 3: 4} |
| over_a_week_late | {'False': 3, 'True': 1} |  |
| over_budget | {'False': 2, 'True': 3} |  |
| over_three_days | {'False': 4, 'True': 5, 'unknown': 1} |  |
| overdue | {'False': 2, 'True': 2, 'unknown': 1} |  |
| panel_majority | {'False': 2, 'True': 2, 'unknown': 1} |  |
| panel_unanimous | {'False': 2, 'True': 2, 'unknown': 1} |  |
| paperwork_missing | {'False': 1, 'True': 3, 'unknown': 1} |  |
| passing_mark | {'False': 4, 'True': 3, 'unknown': 2} |  |
| payroll_involved | {'False': 7, 'True': 4, 'unknown': 3} |  |
| persistence_created | {'False': 4, 'True': 3, 'unknown': 3} |  |
| person_named | {'False': 3, 'True': 2} |  |
| photo_sent | {'False': 2, 'True': 1, 'unknown': 1} |  |
| plan_tier | {'business': 1, 'enterprise': 7, 'free': 4, 'pro': 5, 'unknown': 3} | {0: 2, 1: 4, 2: 6, 3: 5} |
| po_match | {'False': 2, 'True': 2} |  |
| poster_objects | {'False': 10, 'True': 5} |  |
| pressured | {'False': 9, 'True': 11} |  |
| primary_team | {'billing': 4, 'engineering': 6, 'retention': 6, 'success': 4} | {0: 6, 1: 6, 2: 5, 3: 3} |
| priority | {'0': 16, '1': 14, '2': 11, '3': 10, 'unknown': 9} |  |
| product_category | {'clothing': 5, 'electronics': 4, 'groceries': 4, 'home goods': 4, 'unknown': 3} | {0: 4, 1: 4, 2: 6, 3: 3} |
| production_involved | {'False': 9, 'True': 7, 'unknown': 4} |  |
| properly_cited | {'False': 3, 'True': 2, 'unknown': 1} |  |
| public_audience | {'False': 6, 'True': 10, 'unknown': 4} |  |
| reason | {'changed_mind': 5, 'damaged_item': 4, 'not_delivered': 5, 'wrong_item': 6} | {0: 5, 1: 4, 2: 5, 3: 6} |
| receipt_attached | {'False': 3, 'True': 2, 'unknown': 1} |  |
| recent_breach | {'False': 2, 'True': 2, 'unknown': 1} |  |
| recent_change | {'False': 4, 'True': 3, 'unknown': 2} |  |
| recent_denial | {'False': 4, 'unknown': 1} |  |
| recipient_contacted | {'False': 2, 'True': 2, 'unknown': 1} |  |
| referral_on_file | {'False': 4, 'True': 1} |  |
| referred | {'False': 2, 'True': 2, 'unknown': 1} |  |
| refund_asked | {'False': 10, 'True': 9} |  |
| renews_automatically | {'False': 4, 'True': 4, 'unknown': 2} |  |
| repeat_offender | {'False': 8, 'True': 7, 'unknown': 3} |  |
| repeated_attempts | {'False': 2, 'True': 2, 'unknown': 1} |  |
| request_aging | {'False': 3, 'True': 2} |  |
| request_type | {'appointment_request': 5, 'bank_detail_change': 6, 'billing_question': 5, 'claim_denied': 5, 'expense_claim': 6, 'invoice_approval': 4, 'possible_duplicate': 4, 'records_request': 5} | {0: 10, 1: 11, 2: 11, 3: 8} |
| requester_type | {'another clinic': 1, 'family member': 1, 'law firm': 2, 'patient': 1} | {0: 1, 1: 2, 2: 1, 3: 1} |
| response | {'close': 2, 'isolate_host': 7, 'monitor': 4, 'reset_credentials': 3, 'unknown': 4} | {0: 4, 1: 4, 2: 4, 3: 4} |
| review | {'accept': 6, 'investigate': 6, 'retry': 4, 'unknown': 4} | {0: 4, 1: 5, 2: 5, 3: 2} |
| risk | {'0': 11, '1': 8, '2': 7, '3': 7, 'unknown': 7} |  |
| rollback_possible | {'False': 1, 'True': 2} |  |
| rubric_cited | {'False': 2, 'True': 3} |  |
| same_invoice | {'False': 1, 'True': 2, 'unknown': 1} |  |
| senior | {'False': 8, 'True': 8, 'unknown': 4} |  |
| severity | {'0': 9, '1': 11, '2': 12, '3': 12, '4': 5, 'unknown': 11} |  |
| skill_match | {'False': 4, 'True': 4, 'unknown': 2} |  |
| some_support | {'False': 1, 'True': 3, 'unknown': 1} |  |
| source_cited | {'False': 2, 'True': 3} |  |
| spread | {'False': 2, 'True': 3} |  |
| stakes | {'0': 5, '1': 5, '2': 4, '3': 3, 'unknown': 3} |  |
| tests_green | {'False': 2, 'True': 2, 'unknown': 1} |  |
| third_party | {'False': 2, 'True': 3} |  |
| ticket_type | {'access_request': 5, 'hardware': 6, 'outage': 4, 'performance': 5} | {0: 6, 1: 5, 2: 4, 3: 5} |
| time_pressure | {'0': 2, '1': 3, '2': 4, '3': 3, 'unknown': 2} |  |
| touched_production | {'False': 8, 'True': 8, 'unknown': 4} |  |
| tracking_says_delivered | {'False': 2, 'True': 1, 'unknown': 2} |  |
| transient_error | {'False': 2, 'True': 2, 'unknown': 1} |  |
| transport_mode | {'air': 4, 'rail': 4, 'road': 5, 'sea': 3, 'unknown': 4} | {0: 5, 1: 3, 2: 3, 3: 5} |
| travel_expense | {'False': 3, 'True': 2, 'unknown': 1} |  |
| undoable | {'False': 2, 'True': 1, 'unknown': 1} |  |
| unlimited_liability | {'False': 2, 'True': 2, 'unknown': 1} |  |
| urgency | {'critical': 2, 'high': 4, 'low': 4, 'medium': 6, 'unknown': 4} | {0: 2, 1: 4, 2: 4, 3: 6} |
| us_law | {'False': 4, 'True': 4, 'unknown': 2} |  |
| very_late | {'False': 2, 'True': 3} |  |
| violation_type | {'harassment': 5, 'misinformation': 5, 'no_violation': 5, 'spam': 5} | {0: 5, 1: 5, 2: 6, 3: 4} |
| wants_money_back | {'False': 9, 'True': 8, 'unknown': 3} |  |
| warranty | {'False': 3, 'True': 2, 'unknown': 1} |  |
| wide_campaign | {'False': 2, 'True': 3} |  |
| widely_seen | {'False': 8, 'True': 6, 'unknown': 3} |  |
| within_30_days | {'False': 5, 'True': 7, 'unknown': 3} |  |
| workaround_exists | {'False': 5, 'True': 7, 'unknown': 3} |  |
| workaround_works | {'False': 2, 'True': 2, 'unknown': 2} |  |
| year_in_role | {'False': 1, 'True': 4} |  |

Verifier mismatches by fact and mention level (all drafts): threatens_cancel/absent 5, tone/explicit 4, tone/implied 3, reports/explicit 3, wants/absent 3, key_account/implied 3, deadline/absent 2, names_person/absent 2, order_value/explicit 2, category/explicit 2, wants/explicit 2, member/explicit 2, prior_returns/explicit 2, reason/explicit 2, asked_user/absent 2, refund_requested/absent 1, mentions_competitor/absent 1, views/explicit 1, prior_strikes/absent 1, account_age_days/absent 1, auto_hidden/explicit 1, audience/explicit 1, poster_disputes/explicit 1, violation/explicit 1, has_link/absent 1, cites_source/absent 1, new_vendor/implied 1, privileged/absent 1, member/implied 1, days_late/absent 1, tracking_delivered/explicit 1, days_since_delivery/absent 1, photo/explicit 1, new_patient/explicit 1, requester/absent 1, recipient_reached/absent 1, points_disputed/absent 1, product_area/absent 1, affected_users/absent 1
