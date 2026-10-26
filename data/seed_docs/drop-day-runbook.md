# Drop-Day Runbook
Owner: Platform on-call. Applies to every Friday 10:00 limited drop.

## T-60 minutes
Scale the checkout service to 40 pods. Confirm the inventory count in the admin panel matches the drop size. Enable the virtual waiting room.

## T-10 minutes
Drop Club members get early access at 09:50. Watch the checkout error rate dashboard; the alert fires above 2% errors.

## During the drop
If the checkout error rate stays above 2% for 3 minutes, page the payments on-call and post in #drop-war-room. Do not change inventory counts manually during a drop.

## After the drop
Scale checkout back to 8 pods after 30 minutes. File a drop report within 24 hours.

## Drop calendar
Air Glide restock: Friday 2026-10-16 at 10:00, 3,000 pairs, limited drop.
Volt Runner: Friday 2026-05-08 at 10:00, limited drop.
Air Glide original release: Friday 2026-03-13 at 10:00, 5,000 pairs, limited drop.
