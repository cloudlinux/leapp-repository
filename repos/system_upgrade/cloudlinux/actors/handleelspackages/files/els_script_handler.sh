#!/bin/bash

OS_VERSION="$(rpm -q --qf '%{version}' $(rpm -q --whatprovides redhat-release 2>/dev/null) 2>/dev/null | cut -c 1)"
BACKUP="/etc/cl-elevate-saved"
log=/var/log/elevate_els_packages.log

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$log")"
touch "$log"

# Start logging
echo "Starting ELS package handling at $(date)" | tee -a "${log}"

mkdir -p "${BACKUP}" 2>/dev/null || {
    echo "Failed to create backup directory ${BACKUP}" | tee -a "${log}"
    exit 1
}

# Only proceed for CentOS 7
if [[ "$OS_VERSION" != "7" ]]; then
    echo "Not Cloudlinux 7, skipping ELS processing" | tee -a "${log}"
    exit 0
fi

# Check if ELS repositories are present
if ! ls /etc/yum.repos.d/centos*els*.repo &> /dev/null; then
    echo "No ELS repositories found, skipping processing" | tee -a "${log}"
    exit 0
fi

echo "ELS repositories detected. Processing ELS packages before conversion..." | tee -a "${log}"

# Create package backup list
rpm -qa | sort > "${BACKUP}/els_packages_backup_$(date +%Y%m%d_%H%M%S).txt" || {
    echo "Warning: Failed to create package backup list" | tee -a "${log}"
}

# Prevent ELS packages from being reinstalled
if ! grep -q "exclude=\*.tuxcare.els\*" /etc/yum.conf; then
    {
        echo
        echo "# Added by elevate"
        echo "exclude=*.tuxcare.els*"
    } >> /etc/yum.conf || echo "Warning: Failed to add exclusion to yum.conf" | tee -a "${log}"
fi

# Save and disable ELS repos
cp /etc/yum.repos.d/centos*els*.repo "${BACKUP}/" 2>&1 | tee -a "${log}" || true
echo "Disabling ELS repositories..." | tee -a "${log}"
yum-config-manager --disable centos7-els 2>&1 | tee -a "${log}" || true
for i in {1..6}; do
    yum-config-manager --disable centos7els-rollout-$i 2>&1 | tee -a "${log}" || true
done

# Remove els-define package first if present
if rpm -q els-define &> /dev/null; then
    yum remove -y els-define 2>&1 | tee -a "${log}" || echo "Warning: Failed to remove els-define" | tee -a "${log}"
fi

# Get list of installed ELS packages
echo "Checking for ELS packages..." | tee -a "${log}"
els_pkgs=$(rpm -qa | grep -E '\.tuxcare\.els[0-9]') || true

if [ -n "$els_pkgs" ]; then
    echo "Found ELS packages:" | tee -a "${log}"
    echo "$els_pkgs" | tee -a "${log}"

    # Create a yum shell script to handle the transaction
    TMPFILE=$(mktemp)
    echo "# yum shell commands" > "$TMPFILE"

    # Process each package
    while read -r pkg; do
        base_name=$(echo "$pkg" | awk -F'-[0-9]' '{print $1}')
        if [ -n "$base_name" ]; then
            echo "remove $pkg" >> "$TMPFILE"
            echo "install $base_name" >> "$TMPFILE"
        fi
    done <<< "$els_pkgs"

    echo "run" >> "$TMPFILE"
    echo "exit" >> "$TMPFILE"

    # Execute the yum shell script
    echo "Replacing ELS packages with base versions..." | tee -a "${log}"
    if ! yum shell -y "$TMPFILE" 2>&1 | tee -a "${log}"; then
        echo "Trying alternative approach..." | tee -a "${log}"
        while read -r pkg; do
            base_name=$(echo "$pkg" | awk -F'-[0-9]' '{print $1}')
            if [ -n "$base_name" ]; then
                yum downgrade -y "$base_name" 2>&1 | tee -a "${log}" || true
            fi
        done <<< "$els_pkgs"
    fi
    rm -f "$TMPFILE"
fi

# Move ELS repo files to backup and clean up
mv -f /etc/yum.repos.d/centos*els*.repo "${BACKUP}/" 2>&1 | tee -a "${log}" || true

# Remove TuxCare GPG key if it exists
if [ -f "/etc/pki/rpm-gpg/RPM-GPG-KEY-TuxCare" ]; then
    mv -f "/etc/pki/rpm-gpg/RPM-GPG-KEY-TuxCare" "${BACKUP}/" 2>&1 | tee -a "${log}" || true
fi

# Clean yum cache
yum clean all 2>&1 | tee -a "${log}" || true

echo "ELS package handling complete" | tee -a "${log}"
exit 0
