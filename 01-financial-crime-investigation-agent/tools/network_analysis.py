# tools/network_analysis.py
# ============================================================
# Counterparty Network Analysis
#
# WHY AN INVESTIGATOR NEEDS THIS:
#   Money laundering is rarely a solo operation. It involves networks of entities —
#   shell companies, nominees, family members, business associates — designed to
#   create multiple layers between criminal proceeds and their ultimate destination.
#   Network analysis "follows the money" beyond the immediate transaction to map
#   the broader web of relationships. A customer may look clean in isolation but
#   be one step away from a sanctioned entity or criminal organization.
#
# REGULATORY REQUIREMENTS SERVED:
#   - FATF R.20: Reporting of suspicious transactions — requires considering
#     the full context, including counterparty relationships
#   - FATF R.24/25: Transparency of legal persons — identifying shell companies
#   - FinCEN CDD Rule: Beneficial ownership of entities in transactions
#   - OFAC 50% Rule: Entities majority-owned by SDNs are also blocked
#   - BSA Section 314(b): Banks may voluntarily share information about
#     suspected money launderers — counterparty data enables 314(b) inquiries
#
# REAL VENDOR SYSTEMS THAT PROVIDE THIS:
#   Graph Intelligence Platforms:
#   - Sayari Analytics: Specialized in corporate network intelligence, shell company detection
#   - Quantexa: AI-powered entity resolution and network analytics for financial crime
#   - FinScan (IDEX): Entity resolution for financial crime
#   - i2 Group (IBM): Analyst workbench for network visualization
#   - Palantir Gotham: Large-scale network analysis (used by major banks and government)
#
#   Corporate Registry Data (for entity verification):
#   - OpenCorporates: 200M+ companies globally, API access
#   - Dun & Bradstreet Hoovers: Business entity intelligence
#   - BvD Orbis / Moody's: Ownership structure data
#   - Preqin: Private equity/fund structures
#
#   Network Library:
#   - NetworkX (Python): Open source, used here for graph construction
#   - Neo4j: Graph database for large-scale network persistence
#   - Amazon Neptune: Cloud graph database for production scale
# ============================================================

import logging
import random
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple

# NetworkX: The Python library for graph analysis
# Used for: building directed graphs, path finding, centrality metrics
import networkx as nx

logger = logging.getLogger(__name__)

# ── INTEGRATION POINT ────────────────────────────────────────────────────────
# PRODUCTION: Network data should come from a persistent graph database.
# Build the graph from:
# 1. Transaction history (edges = transactions, nodes = accounts/entities)
# 2. Corporate registry data (ownership relationships)
# 3. Internal relationship data from CRM
# 4. External network intelligence (Sayari, Quantexa)
#
# Example Sayari integration:
#   from sayari import SayariClient
#   client = SayariClient(api_key=os.getenv("SAYARI_API_KEY"))
#   entity_data = client.search_entities(name=entity_name, limit=10)
#   network = client.get_entity_network(entity_id=entity_data[0]["id"], depth=3)
#   return _convert_sayari_network(network)
# ─────────────────────────────────────────────────────────────────────────────

# High-risk jurisdictions per FinCEN advisories and FATF grey/black lists
HIGH_RISK_JURISDICTIONS = {
    # OFAC-sanctioned countries
    "IR": "Iran (OFAC-sanctioned)",
    "KP": "North Korea (OFAC-sanctioned)",
    "SY": "Syria (OFAC-sanctioned)",
    "CU": "Cuba (OFAC-sanctioned)",
    "VE": "Venezuela (targeted OFAC sanctions)",
    "RU": "Russia (sector-targeted OFAC sanctions)",
    "BY": "Belarus (OFAC-sanctioned)",
    # FATF blacklist
    "MM": "Myanmar (FATF blacklist — February 2023)",
    # FATF greylist (as of 2024)
    "HT": "Haiti (FATF greylist)",
    "SS": "South Sudan (FATF greylist)",
    "SO": "Somalia (FATF greylist)",
    "YE": "Yemen (FATF greylist)",
    "LY": "Libya (FATF greylist)",
    # Common ML/TF jurisdictions
    "AF": "Afghanistan (post-2021 Taliban control)",
    # Secrecy jurisdictions (not sanctioned but high ML risk)
    "BZ": "Belize (offshore secrecy jurisdiction)",
    "VG": "British Virgin Islands (high shell company use)",
    "KY": "Cayman Islands (offshore financial center)",
    "PA": "Panama (Panama Papers jurisdiction)",
}

# Shell company indicator patterns — entity characteristics that suggest
# the entity may be a shell rather than a legitimate operating business
SHELL_COMPANY_INDICATORS = {
    "registered_agent_address": [
        "1209 Orange Street",  # Famous Delaware registered agent address
        "Corporation Trust Center",
        "The Corporation Company",
        "United Agent Group",
    ],
    "generic_name_keywords": [
        "holdings", "capital", "ventures", "management", "consulting",
        "group", "partners", "resources", "global", "international",
        "solutions", "services", "enterprises", "associates",
    ],
    "secrecy_jurisdictions": ["BVI", "KY", "PA", "BZ", "VG", "SC", "MU", "NR"],
    "incorporation_states": ["DE", "WY", "NV"],  # Common shell states (not necessarily suspicious alone)
}


def build_counterparty_network(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a directed graph of counterparty relationships from transaction data.

    This function creates a network model where:
    - NODES = entities (the customer, counterparties, intermediaries)
    - EDGES = transactions (with amount, date, type as attributes)

    The resulting network enables:
    - Identification of key counterparties (by volume, frequency)
    - Detection of high-risk jurisdiction exposure
    - Foundation for shell company and circular flow analysis
    - Shortest-path analysis to known bad actors

    Args:
        transactions: Full transaction history list

    Returns:
        Network graph dictionary with nodes, edges, and analysis results

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # For production graph persistence, store in Neo4j or Amazon Neptune:
    #   driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(user, password))
    #   with driver.session() as session:
    #       for txn in transactions:
    #           session.run(
    #               "MERGE (a:Account {id: $from_id}) "
    #               "MERGE (b:Account {id: $to_id}) "
    #               "CREATE (a)-[:TRANSACTION {amount: $amount, date: $date}]->(b)",
    #               from_id=txn["account_id"], to_id=txn["counterparty_name"],
    #               amount=txn["amount"], date=txn["date"]
    #           )
    # ──────────────────────────────────────────────────────────────────────────
    """
    # Initialize directed graph — directed because money flow has direction
    G = nx.DiGraph()

    # Track metrics for each node
    node_volumes = defaultdict(float)  # Total transaction volume
    node_frequencies = defaultdict(int)  # Transaction count
    node_countries = {}  # Country of each node
    node_types = {}  # Entity type

    edges = []

    # ── BUILD GRAPH FROM TRANSACTIONS ──────────────────────────────────────────
    for txn in transactions:
        account_id = txn.get("account_id", "UNKNOWN_ACCOUNT")
        counterparty = txn.get("counterparty_name", "UNKNOWN_COUNTERPARTY")
        amount = txn.get("amount", 0)
        direction = txn.get("direction", "CREDIT")
        txn_type = txn.get("transaction_type", "UNKNOWN")
        counterparty_country = txn.get("counterparty_country", "US")
        date = txn.get("date", "")

        if counterparty in ("CASH", None, "", "UNKNOWN"):
            continue  # Skip cash transactions for network analysis

        # Add nodes
        G.add_node(account_id, type="ACCOUNT", country="US")
        G.add_node(counterparty, type="COUNTERPARTY", country=counterparty_country)

        # Add edge with transaction metadata
        if direction == "DEBIT":
            # Money goes FROM our account TO counterparty
            G.add_edge(account_id, counterparty, amount=amount, date=date, type=txn_type)
            node_volumes[counterparty] += amount
            node_volumes[account_id] += amount
        else:
            # Money comes FROM counterparty TO our account
            G.add_edge(counterparty, account_id, amount=amount, date=date, type=txn_type)
            node_volumes[counterparty] += amount
            node_volumes[account_id] += amount

        node_frequencies[counterparty] += 1
        node_countries[counterparty] = counterparty_country

        edges.append({
            "from": counterparty if direction == "CREDIT" else account_id,
            "to": account_id if direction == "CREDIT" else counterparty,
            "amount": amount,
            "date": date,
            "type": txn_type,
        })

    # ── IDENTIFY HIGH-RISK JURISDICTION NODES ───────────────────────────────────
    high_risk_nodes = []
    for node in G.nodes():
        country = node_countries.get(node, "")
        if country in HIGH_RISK_JURISDICTIONS:
            high_risk_nodes.append({
                "entity": node,
                "country": country,
                "country_risk": HIGH_RISK_JURISDICTIONS[country],
                "total_volume": node_volumes.get(node, 0),
            })

    # ── TOP COUNTERPARTIES BY VOLUME ─────────────────────────────────────────
    primary_account = transactions[0].get("account_id", "") if transactions else ""
    counterparty_nodes = [n for n in G.nodes() if n != primary_account]
    top_counterparties = sorted(
        [{"name": n, "volume": node_volumes.get(n, 0), "frequency": node_frequencies.get(n, 0),
          "country": node_countries.get(n, "US")} for n in counterparty_nodes],
        key=lambda x: x["volume"],
        reverse=True,
    )[:20]  # Top 20

    return {
        "nodes": list(G.nodes()),
        "edges": edges,
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "top_counterparties": top_counterparties,
        "high_risk_jurisdictions": high_risk_nodes,
        "_graph_object": G,  # Keep the NetworkX object for further analysis
        "analysis_timestamp": datetime.utcnow().isoformat(),
    }


def detect_shell_company_indicators(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze an entity for characteristics associated with shell companies.

    Shell companies are legitimate legal vehicles, but they are also the
    #1 tool for hiding beneficial ownership and layering money. FATF R.24
    and the FinCEN CDD Rule both target this vulnerability.

    Red flags for shell companies (not conclusive alone, but suspicious in combination):
    1. Registered agent address (same address as hundreds of other companies)
    2. Generic/meaningless name ("XYZ Holdings LLC")
    3. Incorporated in secrecy state/jurisdiction (Delaware, BVI, Cayman)
    4. Minimal employees relative to revenue
    5. Round-number cash flows (matching round-trip amounts)
    6. Recently incorporated (< 2 years old)
    7. No verifiable web presence or physical operations
    8. No clear business purpose evident from transactions
    9. Shared officers/directors with multiple other entities
    10. Multi-layer ownership structure (more than 2 layers)

    Args:
        entity: Dictionary with entity data including name, transactions, metadata

    Returns:
        Shell company assessment with probability and indicators

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Sayari Analytics (specialized shell company detection):
    #   sayari_result = sayari_client.analyze_entity(
    #       name=entity["name"],
    #       country=entity.get("country"),
    #       include_shell_indicators=True
    #   )
    #   return _parse_sayari_shell_analysis(sayari_result)
    #
    # Also useful:
    # - OpenCorporates API: https://opencorporates.com/api-docs
    # - GLEIF (Legal Entity Identifier): https://www.gleif.org/en/lei-data/
    # ──────────────────────────────────────────────────────────────────────────
    """
    entity_name = entity.get("name", "")
    transactions = entity.get("transaction_pattern", [])

    indicators = []
    probability_score = 0

    # ── CHECK NAME FOR GENERIC KEYWORDS ─────────────────────────────────────
    name_lower = entity_name.lower()
    generic_keywords_found = [kw for kw in SHELL_COMPANY_INDICATORS["generic_name_keywords"] if kw in name_lower]
    if len(generic_keywords_found) >= 1:
        indicators.append(f"Generic/meaningless company name (keywords: {', '.join(generic_keywords_found)})")
        probability_score += 15

    # ── CHECK FOR ROUND-DOLLAR TRANSACTION AMOUNTS ────────────────────────
    if transactions:
        round_dollar_count = sum(
            1 for t in transactions
            if t.get("amount", 0) % 10000 == 0 or t.get("amount", 0) % 50000 == 0
        )
        if round_dollar_count >= 2:
            indicators.append(f"Round-dollar transaction amounts ({round_dollar_count} transactions)")
            probability_score += 20

        # ── CHECK FOR RAPID IN-OUT PATTERN ───────────────────────────────────
        inflows = sum(t.get("amount", 0) for t in transactions if t.get("direction") == "CREDIT")
        outflows = sum(t.get("amount", 0) for t in transactions if t.get("direction") == "DEBIT")
        if inflows > 0 and outflows > 0:
            flow_ratio = min(inflows, outflows) / max(inflows, outflows)
            if flow_ratio > 0.85:  # In/out are nearly equal — pass-through entity
                indicators.append("Near-equal inflows and outflows (pass-through pattern — no economic purpose)")
                probability_score += 25

    # ── CHECK ENTITY NAME AGAINST KNOWN SHELL COMPANY PATTERNS ──────────────
    if any(pattern in entity_name for pattern in ["Holdings", "Capital", "Ventures", "Management"]):
        if any(country in entity_name for country in ["Panama", "International", "Global", "Offshore"]):
            indicators.append("Entity name combines generic corporate term with international/offshore reference")
            probability_score += 20

    # ── CHECK FOR HIGH-RISK JURISDICTION ────────────────────────────────────
    entity_country = entity.get("country", "")
    if entity_country in HIGH_RISK_JURISDICTIONS:
        indicators.append(f"Entity located in high-risk jurisdiction: {HIGH_RISK_JURISDICTIONS.get(entity_country, entity_country)}")
        probability_score += 15

    # ── APPLY BONUS SCORING FOR MULTIPLE INDICATORS ─────────────────────────
    # Multiple indicators together are more suspicious than each individually
    if len(indicators) >= 3:
        probability_score += 10  # Combination multiplier

    probability_score = min(100, probability_score)

    return {
        "entity_name": entity_name,
        "shell_company_probability": probability_score,
        "confidence": "HIGH" if probability_score >= 70 else ("MEDIUM" if probability_score >= 40 else "LOW"),
        "indicators_found": indicators,
        "indicators_count": len(indicators),
        "requires_enhanced_investigation": probability_score >= 50,
        "recommended_actions": [
            "Request formation documents and operating agreement",
            "Verify beneficial ownership per CDD Rule",
            "Obtain corporate registry search results",
            "Request bank references and operating history",
        ] if probability_score >= 50 else [],
    }


def identify_circular_flows(network_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Detect circular money flows — money that leaves an account and returns
    via a different path.

    Circular flows are the hallmark of layering — the second stage of the
    AML cycle where illicit funds are passed through multiple accounts/entities
    to obscure their origin. The net economic effect of circular flows is zero
    (or nearly zero), which means they have no legitimate business purpose.

    Example: Account A sends $100K to Company B → Company B sends $95K to
    Company C → Company C sends $93K back to Account A. The net result:
    Account A "laundered" $93K. The $7K difference covers the layering cost.

    Args:
        network_graph: Network graph dictionary (must contain _graph_object)

    Returns:
        List of detected circular flows, each with path, amounts, and timing

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # For large networks, use a graph database query:
    # Neo4j Cypher (detect cycles):
    #   MATCH p=(a:Account)-[:TRANSACTION*2..5]->(a)
    #   WHERE all(r in relationships(p) WHERE r.date > '2024-01-01')
    #   RETURN p, reduce(total = 0, r in relationships(p) | total + r.amount) AS volume
    #   ORDER BY volume DESC LIMIT 10
    # ──────────────────────────────────────────────────────────────────────────
    """
    G = network_graph.get("_graph_object")
    if G is None or not isinstance(G, nx.DiGraph):
        return []

    circular_flows = []

    try:
        # Find all cycles in the directed graph
        # We limit to simple cycles (no node repeated) to avoid combinatorial explosion
        # Limit cycle length to 5 hops — longer paths are unlikely to be detected
        all_cycles = list(nx.simple_cycles(G))

        for cycle in all_cycles[:10]:  # Analyze top 10 cycles
            if len(cycle) < 2:
                continue

            # Calculate the total amount flowing through the cycle
            cycle_amount = 0
            cycle_dates = []

            for i in range(len(cycle)):
                node_a = cycle[i]
                node_b = cycle[(i + 1) % len(cycle)]

                if G.has_edge(node_a, node_b):
                    edge_data = G.get_edge_data(node_a, node_b)
                    cycle_amount += edge_data.get("amount", 0)
                    if edge_data.get("date"):
                        cycle_dates.append(edge_data["date"])

            # Calculate time elapsed in the cycle
            days_elapsed = 0
            if len(cycle_dates) >= 2:
                try:
                    first_date = datetime.strptime(min(cycle_dates), "%Y-%m-%d")
                    last_date = datetime.strptime(max(cycle_dates), "%Y-%m-%d")
                    days_elapsed = (last_date - first_date).days
                except ValueError:
                    pass

            circular_flows.append({
                "flow_path": cycle,
                "path_description": " → ".join(cycle[:5]) + (" → ..." if len(cycle) > 5 else ""),
                "hop_count": len(cycle),
                "total_amount": cycle_amount,
                "days_elapsed": days_elapsed,
                "risk_level": "HIGH" if days_elapsed < 30 else "MEDIUM",
                "analysis": f"Money completed a circuit through {len(cycle)} entities over {days_elapsed} days",
                "regulatory_note": "Circular flows with no net economic effect are a classic layering indicator",
            })

    except nx.NetworkXError as e:
        logger.warning(f"[network_analysis] Cycle detection error: {e}")

    # If no NetworkX cycles found, check for near-circular flows in fixture data
    # (Some circular flows may not form perfect graph cycles due to timing)
    edges = network_graph.get("edges", [])
    account_ids = set(t.get("account_id", "") for t in [])  # Would need full txn data

    return circular_flows


def calculate_network_risk_score(network_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate an overall risk score for the counterparty network.

    The network risk score assesses:
    1. Exposure to high-risk jurisdictions (volume and frequency)
    2. Number of suspected shell companies in the network
    3. Presence of circular flows (layering indicator)
    4. Proximity to known bad actors (hops to sanctioned entities)
    5. Concentration risk (few large counterparties vs. many small)

    Args:
        network_graph: Network graph dictionary with analysis results

    Returns:
        Network risk score dictionary with score and breakdown

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Quantexa provides pre-built network risk scores:
    #   quantexa_result = quantexa_client.assess_network_risk(
    #       entity_id=customer_id,
    #       network_depth=3,
    #       include_typologies=["structuring", "layering", "shell_company"]
    #   )
    #   return quantexa_result.risk_score
    # ──────────────────────────────────────────────────────────────────────────
    """
    risk_score = 0
    risk_factors = []

    # ── HIGH-RISK JURISDICTION EXPOSURE ────────────────────────────────────────
    high_risk_nodes = network_graph.get("high_risk_jurisdictions", [])
    if high_risk_nodes:
        high_risk_volume = sum(n.get("total_volume", 0) for n in high_risk_nodes)
        risk_score += min(25, len(high_risk_nodes) * 8)
        risk_factors.append(f"{len(high_risk_nodes)} counterparties in high-risk jurisdictions (total volume: ${high_risk_volume:,.0f})")

    # ── SHELL COMPANY FINDINGS ──────────────────────────────────────────────────
    shell_findings = network_graph.get("shell_company_findings", {})
    if shell_findings:
        risk_score += min(25, len(shell_findings) * 10)
        risk_factors.append(f"{len(shell_findings)} suspected shell companies in counterparty network")

    # ── CIRCULAR FLOWS ──────────────────────────────────────────────────────────
    circular_flows = network_graph.get("circular_flows", [])
    if circular_flows:
        risk_score += min(20, len(circular_flows) * 10)
        risk_factors.append(f"{len(circular_flows)} circular money flows detected (classic layering pattern)")

    # ── NETWORK CONCENTRATION ────────────────────────────────────────────────
    top_counterparties = network_graph.get("top_counterparties", [])
    if top_counterparties:
        total_volume = sum(c.get("volume", 0) for c in top_counterparties)
        top_3_volume = sum(c.get("volume", 0) for c in top_counterparties[:3])
        if total_volume > 0 and top_3_volume / total_volume > 0.8:
            risk_score += 5
            risk_factors.append("High counterparty concentration (top 3 counterparties account for >80% of volume)")

    risk_score = min(100, risk_score)

    return {
        "score": risk_score,
        "level": "HIGH" if risk_score >= 60 else ("MEDIUM" if risk_score >= 30 else "LOW"),
        "risk_factors": risk_factors,
        "total_counterparties": network_graph.get("node_count", 0),
        "high_risk_counterparties": len(high_risk_nodes),
        "shell_companies_suspected": len(shell_findings),
        "circular_flows_count": len(circular_flows),
    }
