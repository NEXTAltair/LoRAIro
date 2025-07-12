#!/bin/bash
set -euo pipefail

# Initialize firewall for development container
# Based on Claude Code's firewall configuration but adapted for LoRAIro

echo "Initializing firewall..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root"
   exit 1
fi

# Function to validate IP range
validate_ip_range() {
    local ip_range="$1"
    if [[ $ip_range =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]]; then
        return 0
    else
        echo "Invalid IP range: $ip_range"
        return 1
    fi
}

# Flush existing rules
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Allow established connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH (port 22)
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A OUTPUT -p tcp --sport 22 -j ACCEPT

# Allow DNS
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Allow HTTP/HTTPS for package downloads and API access
iptables -A OUTPUT -p tcp --dport 80 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT

# Create ipset for allowed domains
ipset create allowed_domains hash:net 2>/dev/null || ipset flush allowed_domains

# Add common development and AI service IP ranges
echo "Adding allowed IP ranges..."

# GitHub IP ranges (for git operations)
GITHUB_IPS=$(curl -s https://api.github.com/meta | jq -r '.git[]' 2>/dev/null || echo "140.82.112.0/20 192.30.252.0/22")
for ip in $GITHUB_IPS; do
    if validate_ip_range "$ip"; then
        ipset add allowed_domains "$ip" 2>/dev/null || true
    fi
done

# Common package registry IP ranges
COMMON_IPS=(
    "185.199.108.0/22"  # GitHub Pages/CDN
    "151.101.0.0/16"    # Fastly CDN (PyPI)
    "104.16.0.0/13"     # Cloudflare
    "172.217.0.0/16"    # Google services
    "142.250.0.0/15"    # Google services
)

for ip in "${COMMON_IPS[@]}"; do
    if validate_ip_range "$ip"; then
        ipset add allowed_domains "$ip" 2>/dev/null || true
    fi
done

# Detect and allow host network
HOST_NETWORK=$(ip route | grep default | awk '{print $3}' | head -1)
if [[ -n "$HOST_NETWORK" ]]; then
    HOST_SUBNET=$(ip route | grep "$HOST_NETWORK" | grep -v default | awk '{print $1}' | head -1)
    if [[ -n "$HOST_SUBNET" ]] && validate_ip_range "$HOST_SUBNET"; then
        echo "Adding host network: $HOST_SUBNET"
        ipset add allowed_domains "$HOST_SUBNET" 2>/dev/null || true
    fi
fi

# Allow outbound traffic to allowed domains
iptables -A OUTPUT -m set --match-set allowed_domains dst -j ACCEPT

# Set default policies
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

echo "Firewall configuration completed."

# Test connectivity
echo "Testing connectivity..."
if curl -s --max-time 5 https://www.google.com > /dev/null; then
    echo "✓ Internet connectivity working"
else
    echo "✗ Internet connectivity failed"
fi

if curl -s --max-time 5 https://api.github.com > /dev/null; then
    echo "✓ GitHub API connectivity working"
else
    echo "✗ GitHub API connectivity failed"
fi

echo "Firewall initialization complete."