# Checkout Error Codes
Owner: Payments team. Use this page when a customer reports an error code at checkout.

## E-4012 Payment hold
The card issuer requires extra verification (3-D Secure). The customer must approve the payment in their banking app. The cart is held for 10 minutes while they do this. Tell the customer: "Your bank is asking you to confirm this payment. Open your banking app and approve it within 10 minutes; your pair is reserved until then." The customer has not been charged until approval.

## E-4029 Too many attempts
The checkout rate limiter blocked the request after 5 checkout attempts in one minute. Ask the customer to wait 60 seconds and try once. Introduced after INC-2051.

## E-5031 Inventory timeout
The inventory service did not answer in time. The customer has not been charged. Ask them to retry; if the drop has sold out, the product page will say so.

## E-5090 Unknown error
Collect the order reference and escalate to the on-call payments engineer.
