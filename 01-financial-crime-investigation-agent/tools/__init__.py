# tools/__init__.py
# Financial Crime Investigation Agent — Tools Package
#
# This package contains mock implementations of all external system integrations
# used in the AML investigation workflow. Each tool file includes:
#   1. Why an investigator needs this data source
#   2. What regulatory requirement it serves
#   3. What real vendor systems provide it
#   4. Clear integration point markers for production system connections
#
# Mock vs. Production:
#   All tools in this package return realistic mock data for demonstration.
#   In production, each function body would be replaced with a real API call
#   to the bank's actual systems. The function signatures, parameters, and
#   return schemas remain identical — only the implementation changes.
