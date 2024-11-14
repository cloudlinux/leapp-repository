#!/bin/bash

BACKUP="/etc/cl-elevate-saved"
RUNNING_KERNEL=$(uname -r)
TMP="${BACKUP}/tmp"

echo "Starting ELS package handling"
echo "Running kernel: ${RUNNING_KERNEL}"

mkdir -p "${BACKUP}" "${TMP}" 2>/dev/null || {
    echo "Failed to create backup/temp directories"
    exit 1
}

# Check if ELS repositories are present
if ! ls /etc/yum.repos.d/centos*els*.repo &> /dev/null; then
    echo "No ELS repositories found, skipping processing"
    rm -rf "${TMP}"
    exit 0
fi

echo "ELS repositories detected. Processing ELS packages before conversion..."

# Create package backup list
rpm -qa | sort > "${BACKUP}/els_packages_backup_$(date +%Y%m%d_%H%M%S).txt" || {
    echo "Warning: Failed to create package backup list"
}

# Function to check if kernel is in use
is_kernel_in_use() {
    local kernel_pkg=$1
    local kernel_ver=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}' "$kernel_pkg")
    [[ "$kernel_ver" == "$RUNNING_KERNEL" ]]
}

# Prevent ELS packages from being reinstalled
if ! grep -q "exclude=\*.tuxcare.els\*" /etc/yum.conf; then
    {
        echo
        echo "# Added by cloudlinux Elevate"
        echo "exclude=*.tuxcare.els*"
    } >> /etc/yum.conf || echo "Warning: Failed to add exclusion to yum.conf"
fi

# Save and disable ELS repos
cp /etc/yum.repos.d/centos*els*.repo "${BACKUP}/" 2>&1
echo "Disabling ELS repositories..."
yum-config-manager --disable centos7-els 2>&1
yum-config-manager --disable 'centos7els-rollout-*' 2>&1

# Remove els-define package first if present
if rpm -q els-define &> /dev/null; then
    yum remove -y els-define 2>&1 || echo "Warning: Failed to remove els-define"
fi

# Get list of installed ELS packages
echo "Checking for ELS packages..."
els_pkgs=$(rpm -qa | grep -E '\.tuxcare\.els[0-9]') || true

if [ -n "$els_pkgs" ]; then
    echo "Found ELS packages:"
    echo "$els_pkgs"

    # Handle kernel packages separately and more aggressively
    els_kernel_pkgs=$(echo "$els_pkgs" | grep "^kernel") || true
    if [ -n "$els_kernel_pkgs" ]; then
        echo "Found ELS kernel packages:"
        echo "$els_kernel_pkgs"

        # Remove all ELS kernel packages, regardless of running kernel
        # since we already have the LVE kernel installed
        echo "Removing all ELS kernel packages since LVE kernel is present..."
        for kernel_pkg in $els_kernel_pkgs; do
            echo "Removing ELS kernel package: $kernel_pkg"
            rpm -e --nodeps "$kernel_pkg" 2>&1 || {
                echo "Warning: Failed to remove $kernel_pkg"
                # If rpm -e fails, try with yum as fallback
                yum remove -y "$kernel_pkg" 2>&1
            }
        done
    fi

    # Process remaining non-kernel ELS packages
    non_kernel_els_pkgs=$(echo "$els_pkgs" | grep -v "^kernel") || true
    if [ -n "$non_kernel_els_pkgs" ]; then
        echo "Processing non-kernel ELS packages..."

        # Create a yum shell script for batch processing
        TMPFILE="${TMP}/yum_commands_$$"
        echo "# yum shell commands" > "$TMPFILE"

        echo "$non_kernel_els_pkgs" | while read -r pkg; do
            base_name=$(echo "$pkg" | awk -F'-[0-9]' '{print $1}')
            if [ -n "$base_name" ]; then
                echo "remove $pkg" >> "$TMPFILE"
                echo "install $base_name" >> "$TMPFILE"
            fi
        done

        echo "run" >> "$TMPFILE"
        echo "exit" >> "$TMPFILE"

        # Execute the yum shell script
        echo "Replacing non-kernel ELS packages with base versions..."
        if ! yum shell -y "$TMPFILE" 2>&1; then
            echo "Trying alternative approach for non-kernel packages..."
            echo "$non_kernel_els_pkgs" | while read -r pkg; do
                base_name=$(echo "$pkg" | awk -F'-[0-9]' '{print $1}')
                if [ -n "$base_name" ]; then
                    yum downgrade -y "$base_name" 2>&1
                fi
            done
        fi
        rm -f "$TMPFILE"
    fi
fi

# Move ELS repo files to backup and clean up
mv -f /etc/yum.repos.d/centos*els*.repo "${BACKUP}/" 2>&1

# Remove TuxCare GPG key if it exists
if [ -f "/etc/pki/rpm-gpg/RPM-GPG-KEY-TuxCare" ]; then
    mv -f "/etc/pki/rpm-gpg/RPM-GPG-KEY-TuxCare" "${BACKUP}/" 2>&1
fi

# Clean up
yum clean all 2>&1
rm -rf "${TMP}"

echo "ELS package handling complete"
exit 0
