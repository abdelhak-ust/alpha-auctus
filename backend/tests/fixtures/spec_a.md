# Acme Portal — Product Spec v1

## 1. Authentication

### 1.1 Single sign-on

Users sign in with SSO through Okta. Password login is not offered for employees.

### 1.2 Session timeout

Sessions expire after 30 minutes of inactivity. The user is returned to the sign-in page.

## 2. Administration

### 2.1 Audit log export

Admins can export the audit log as CSV. The export covers the last 90 days.

## 3. Integrations

The single sign-on flow must also support Azure AD for customers who do not use Okta.
