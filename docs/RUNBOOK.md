# Operations Runbook

This document covers deployment, monitoring, and operational procedures for the Multi-Bagger Research System.

## Local Development Setup

### Prerequisites
- Python 3.10+
- Git
- Make (or equivalent task runner)

### First-Time Setup
```bash
# Clone repository
git clone <repository-url>
cd multi-bagger-research

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
# or on Windows: 
# powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Complete setup
make setup

# Verify installation
make check
```

### Configuration
1. **Copy templates**:
   ```bash
   cp config.example.yml config.yml
   cp .env.example .env
   ```

2. **Edit config.yml** for your preferences:
   ```yaml
   markets: [US]                    # Start with US only
   universe:
     size_target: 1000              # Smaller for development
   dev:
     sample_mode: true              # Use sample data
     sample_size: 50
   ```

3. **Add API keys to .env** (optional for initial setup):
   ```bash
   ALPHA_VANTAGE_KEY=your_key_here
   FMP_API_KEY=your_key_here
   ```

### Development Workflow
```bash
# Run tests and linting
make check

# Format code automatically  
make format

# Run monthly pipeline (placeholder)
make run-monthly

# View logs
make logs

# Check system status
make status
```

## Production Deployment

### Server Requirements
- **OS**: Ubuntu 22.04 LTS (recommended)
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Storage**: 20GB available space
- **Python**: 3.10+ installed

### Production Setup
```bash
# On production server
git clone <repository-url>
cd multi-bagger-research

# Install system dependencies
sudo apt update
sudo apt install -y python3.10 python3-pip make curl

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Setup project
make setup

# Configure for production
cp config.example.yml config.yml
cp .env.example .env

# Edit production config
nano config.yml  # Set appropriate universe size, disable debug mode
nano .env        # Add production API keys
```

### Production Configuration
```yaml
# config.yml - Production settings
markets: [US]
universe:
  size_target: 5000                # Full universe
dev:
  debug_mode: false
  sample_mode: false
  skip_cache: false

logging:
  level: INFO                      # Reduce log verbosity
  file: "logs/multibagger.log"

execution:
  max_runtime_minutes: 120         # Allow longer runs
  parallel_workers: 8              # Use more workers
```

## Scheduling via Cron

### Install Monthly Cron Job
```bash
# Automated install via Makefile
make cron-install

# Manual cron entry (runs 1st of each month at midnight)
crontab -e
# Add line:
0 0 1 * * cd /path/to/multi-bagger-research && make run-monthly >> /var/log/multibagger-cron.log 2>&1
```

### Cron Job Examples
```bash
# Monthly on 1st at midnight
0 0 1 * * cd /path/to/project && make run-monthly

# Monthly on 1st at 2 AM (avoid peak hours)
0 2 1 * * cd /path/to/project && make run-monthly

# Weekly on Sundays (for testing)
0 0 * * 0 cd /path/to/project && make run-monthly

# Daily monitoring (separate from monthly runs)
0 9 * * * cd /path/to/project && make monitor
```

### Remove Cron Job
```bash
make cron-uninstall
```

## Database Operations

### Initialize Database
```bash
# Initialize new database with schema
multibagger db-init

# Initialize with custom path
multibagger db-init --db-path /custom/path/research.db
```

### Verify Database Health
```bash
# Verify schema integrity
multibagger db-verify

# Get detailed database info
multibagger db-info

# Check table record counts and schema version
multibagger db-info
```

### Create Snapshots
```bash
# Create monthly snapshot (automatic timestamp)
multibagger db-snapshot

# Create snapshot in custom location
multibagger db-snapshot --snapshot-dir archives/2025-11

# Monthly snapshots (typically part of pipeline)
multibagger monthly  # Creates snapshot automatically
```

### Database Maintenance
```bash
# Check database file size
ls -lh data/multibagger.db

# Verify database integrity (SQLite native)
sqlite3 data/multibagger.db "PRAGMA integrity_check;"

# Optimize database (reclaim space)
sqlite3 data/multibagger.db "VACUUM;"

# Analyze query performance
sqlite3 data/multibagger.db "ANALYZE;"
```

## Monitoring & Alerting

### Log Monitoring
```bash
# View real-time logs
make logs

# Check recent logs
tail -n 50 logs/multibagger.log

# Search for errors
grep ERROR logs/multibagger.log

# Monitor during monthly run
tail -f logs/multibagger.log
```

### Health Checks
```bash
# System status
make status

# Database status
multibagger db-info

# Check last run results
ls -la snapshots/$(date +%Y-%m)/

# Verify database
multibagger db-verify
```

### Alert Configuration
Configure alerts in `.env`:
```bash
# Email alerts
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_USERNAME=alerts@yourdomain.com
EMAIL_PASSWORD=your_app_password

# Webhook alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

## Backup Procedures

### Database Backup
```bash
# Create backup before monthly run
cp data/multibagger.db backups/multibagger-$(date +%Y%m%d).db

# Compress old backups
gzip backups/multibagger-*.db

# Cleanup old backups (keep last 12 months)
find backups/ -name "*.db.gz" -mtime +365 -delete
```

### Snapshot Management
```bash
# Archive old snapshots
tar -czf archives/snapshots-$(date +%Y).tar.gz snapshots/

# Remove snapshots older than 2 years
find snapshots/ -type d -name "20[0-9][0-9]-*" -mtime +730 -exec rm -rf {} +
```

## Troubleshooting

### Common Issues

**1. Monthly Run Fails to Start**
```bash
# Check cron job
crontab -l | grep multibagger

# Check cron logs
sudo tail /var/log/cron

# Test run manually
cd /path/to/project && make run-monthly
```

**2. Out of Memory During Processing**
```bash
# Check memory usage
free -h

# Reduce parallel workers in config.yml
execution:
  parallel_workers: 2  # Reduce from 8

# Enable sample mode for testing
dev:
  sample_mode: true
  sample_size: 100
```

**3. API Rate Limit Exceeded**
```bash
# Check rate limit configuration
grep rate_limits config.yml

# Reduce workers or add delays
execution:
  parallel_workers: 1
  
# Check API key quotas
curl "https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=YOUR_API_KEY"
```

**4. Database Lock Errors**
```bash
# Check for concurrent access
ps aux | grep multibagger

# Kill hanging processes
pkill -f multibagger

# Rebuild database if corrupted
rm data/multibagger.db
make run-monthly  # Will recreate
```

### Performance Optimization

**Disk Space Management**:
```bash
# Check disk usage
df -h

# Clean old logs
find logs/ -name "*.log" -mtime +30 -delete

# Compress large files
gzip logs/multibagger.log.*
```

**Memory Optimization**:
```bash
# Monitor memory during runs
watch -n 5 'free -h && ps aux | grep multibagger'

# Reduce chunk sizes in config
execution:
  chunk_size: 50  # Reduce from 100
```

## Security

### File Permissions
```bash
# Secure configuration files
chmod 600 .env config.yml

# Secure data directory
chmod 700 data/

# Secure log files
chmod 640 logs/*.log
```

### API Key Management
- Store API keys only in `.env` file
- Use environment-specific keys (dev vs prod)
- Rotate keys regularly
- Monitor usage quotas

### Network Security
- Run on private server (no public access needed)
- Use SSH for server access only
- Consider VPN for additional security
- Monitor failed login attempts

## Maintenance

### Monthly Tasks
- [ ] Review monthly run logs for errors
- [ ] Check database size and performance  
- [ ] Verify backup creation
- [ ] Update dependencies if needed

### Quarterly Tasks
- [ ] Security audit of dependencies
- [ ] Performance review of monthly runs
- [ ] Cleanup old snapshots and logs
- [ ] Review and update configuration

### Annual Tasks
- [ ] Major dependency updates
- [ ] Server OS updates and patches
- [ ] Archive historical data
- [ ] Review and test disaster recovery

## Emergency Procedures

### System Recovery
```bash
# Complete system rebuild
git clone <repository-url>
cd multi-bagger-research
make setup

# Restore from backup
cp backups/multibagger-latest.db data/multibagger.db

# Resume operations
make run-monthly
```

### Data Loss Recovery
```bash
# Restore from git history
git log --oneline snapshots/

# Restore from database backup
sqlite3 data/multibagger.db < backups/schema.sql

# Re-run analysis for current month
make run-monthly --force
```

## Support Contacts

**Technical Issues**:
- Repository Issues: GitHub Issues tracker
- Configuration Help: See docs/BOOTSTRAP.md
- Performance Issues: Check system resources first

**Data Issues**:
- API Problems: Check provider status pages
- Database Issues: Verify disk space and permissions
- Missing Reports: Check logs for pipeline failures

This runbook should cover 90% of operational scenarios. For complex issues, consult the source code and add new procedures to this document.
