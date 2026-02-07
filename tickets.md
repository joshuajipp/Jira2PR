# Jira Tickets - E-Commerce Platform

---

## ECOM-101: Add product inventory check to product service

**Project:** product-service
**Type:** Feature
**Priority:** High
**Status:** To Do

### Description

Currently, the `ProductService` in the product-service has no way to track or check stock availability. We need to add a `stockQuantity` management capability to the product service layer.

### Requirements

- Add a new method `updateStockQuantity(productId: string, quantity: number): Product | null` to `ProductService` in `product-service/src/services/product.service.ts` that updates the `stockQuantity` field on a product.
- Quantity must not be negative; throw an error if a negative value is passed.
- Add a method `getOutOfStockProducts(): Product[]` that returns all products where `stockQuantity === 0` and `isActive === true`.
- Add a method `getLowStockProducts(threshold: number): Product[]` that returns active products with stockQuantity below the given threshold.

### Acceptance Criteria

- [ ] `updateStockQuantity` correctly sets the stock quantity on a product
- [ ] `updateStockQuantity` throws an error when given a negative number
- [ ] `updateStockQuantity` returns null if product does not exist
- [ ] `getOutOfStockProducts` returns only active products with zero stock
- [ ] `getLowStockProducts` returns active products below the threshold
- [ ] All new methods have corresponding unit tests in `product-service/src/__tests__/product.service.test.ts`

---

## ECOM-102: Add partial order cancellation support to order service

**Project:** order-service
**Type:** Feature
**Priority:** High
**Status:** To Do

### Description

Currently, the order service only supports full order cancellation. We need to support cancelling individual items from an order, which reduces the order total.

### Requirements

- Add a new method `cancelOrderItem(String orderId, String itemId, String reason)` to `OrderService` in `order-service/src/main/java/com/ecommerce/order/service/OrderService.java`.
- The method should only work on orders in `PENDING` or `CONFIRMED` status.
- When an item is removed, `recalculateTotals()` must be called on the order.
- If all items are cancelled, the entire order status should transition to `CANCELLED`.
- Throw `IllegalArgumentException` if the order or item is not found.
- Throw `IllegalStateException` if the order is not in a cancellable status.

### Acceptance Criteria

- [ ] Can cancel a single item from a multi-item order
- [ ] Order totals are recalculated after item removal
- [ ] Order automatically transitions to CANCELLED when last item is removed
- [ ] Cannot cancel items from orders in SHIPPED, DELIVERED, etc. status
- [ ] Proper exceptions thrown for invalid inputs
- [ ] Unit tests added to `OrderServiceTest.java`

---

## ECOM-103: Add discount code support to payment service

**Project:** payment-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

The payment service needs to support applying discount codes to payments before processing. This feature allows a discount amount to be subtracted from the payment total.

### Requirements

- Add a new `DiscountCode` struct in `payment-service/models/` with fields: `Code string`, `DiscountType string` (either `"percentage"` or `"fixed"`), `Value float64`, `MinOrderAmount float64`, `MaxUses int`, `CurrentUses int`, `IsActive bool`.
- Add a new method `ApplyDiscount(paymentID string, discountCode string) (*Payment, error)` to `PaymentService` in `payment-service/services/payment_service.go`.
- The method should validate that the payment is in `pending` status, the discount code exists and is active, hasn't exceeded max uses, and the payment amount meets the minimum.
- For percentage discounts, reduce the amount by the percentage. For fixed discounts, subtract the fixed value. The payment amount should never go below zero.
- Store discount codes in-memory within the PaymentService (a map of code string to DiscountCode struct).
- Add a method `RegisterDiscountCode(code DiscountCode) error` to add new codes.

### Acceptance Criteria

- [ ] Can register a new discount code
- [ ] Can apply a percentage discount to a pending payment
- [ ] Can apply a fixed amount discount to a pending payment
- [ ] Payment amount never goes below zero after discount
- [ ] Cannot apply discount to already-processed payment
- [ ] Cannot apply inactive or exhausted discount codes
- [ ] Discount code use count is incremented on successful application
- [ ] Unit tests in `payment-service/services/payment_service_test.go`

---

## ECOM-104: Add inter-warehouse stock transfer to inventory service

**Project:** inventory-service
**Type:** Feature
**Priority:** High
**Status:** To Do

### Description

The inventory service currently has a `TRANSFER` movement type defined in the `StockMovement` model, but there is no actual transfer functionality implemented in the `StockService`. We need to add the ability to transfer stock between warehouses.

### Requirements

- Add a new method `transfer_stock(self, source_item_id: str, destination_warehouse_id: str, quantity: int, notes: str = "") -> tuple[InventoryItem, InventoryItem]` to `StockService` in `inventory-service/services/stock_service.py`.
- The method should:
  1. Validate that the source item exists and has sufficient available quantity
  2. Validate that the destination warehouse exists and is active
  3. Find or create the corresponding inventory item in the destination warehouse (same product_id and sku)
  4. Deduct quantity from source, add to destination
  5. Record two `StockMovement` entries: one OUTBOUND from source warehouse and one INBOUND to destination, both with movement_type `TRANSFER` and the `destination_warehouse_id` field populated
  6. Verify the destination item would not exceed its `max_quantity`
- Return a tuple of (source_item, destination_item).

### Acceptance Criteria

- [ ] Stock is correctly moved from source to destination warehouse
- [ ] Two stock movement records are created (one per warehouse)
- [ ] Cannot transfer more than available quantity
- [ ] Cannot transfer to an inactive warehouse
- [ ] Creates new inventory item in destination if it doesn't exist
- [ ] Validates destination won't exceed max capacity
- [ ] Unit tests in `inventory-service/tests/test_stock_service.py`

---

## ECOM-105: Add notification preference management to notification service

**Project:** notification-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

Users should be able to set notification preferences indicating which channels they want to receive notifications on, and the notification service should respect these preferences.

### Requirements

- Create a new file `notification-service/src/services/preference.service.js` with a `PreferenceService` class.
- The service should manage user notification preferences with methods:
  - `setPreferences(userId, { email: bool, sms: bool, push: bool })` - Set channel preferences for a user
  - `getPreferences(userId)` - Get preferences (default: all channels enabled)
  - `isChannelEnabled(userId, channel)` - Check if a specific channel is enabled
  - `unsubscribeAll(userId)` - Disable all channels
  - `getSubscribedUsers(channel)` - Get list of userIds with a specific channel enabled
- Update `NotificationService.sendNotification()` in `notification-service/src/services/notification.service.js` to check user preferences before sending. If the requested channel is disabled for the user, throw an error with message `"User has disabled {channel} notifications"`.

### Acceptance Criteria

- [ ] Can set and retrieve user notification preferences
- [ ] Default preferences have all channels enabled
- [ ] `sendNotification` checks preferences before dispatching
- [ ] Sending to a disabled channel throws appropriate error
- [ ] `unsubscribeAll` disables all channels
- [ ] `getSubscribedUsers` returns correct user list
- [ ] Unit tests in `notification-service/src/__tests__/preference.service.test.js`
- [ ] Updated tests in `notification-service/src/__tests__/notification.service.test.js` for preference checking

---

## ECOM-106: Add free shipping threshold to shipping rate calculator

**Project:** shipping-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

The shipping service rate calculator should support a "free shipping" threshold. When the order subtotal exceeds a configurable amount, the cheapest ground shipping option should be returned with a rate of $0.00.

### Requirements

- Add a new method `GetRatesWithFreeShipping(req RateRequest, orderSubtotal float64, freeShippingThreshold float64) ([]ShippingRate, error)` to `RateCalculator` in `shipping-service/services/rate_calculator.go`.
- If `orderSubtotal >= freeShippingThreshold`, find the cheapest "ground" service type rate across all carriers and set its `Rate` to `0.00`, marking it as `"free_shipping"` service type. Include this as the first rate in the returned list, followed by all other rates at their normal prices.
- If the threshold is not met, return all rates normally (same as `GetAllRates`).
- If `freeShippingThreshold` is 0 or negative, return error.

### Acceptance Criteria

- [ ] Returns free shipping rate when order subtotal meets threshold
- [ ] Free shipping rate appears first in the list with $0.00 rate
- [ ] Other rates are still returned at normal prices alongside the free option
- [ ] Returns normal rates when threshold is not met
- [ ] Returns error for invalid threshold value
- [ ] Unit tests added to `shipping-service/services/rate_calculator_test.go`

---

## ECOM-107: Add user search functionality to user service

**Project:** user-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

The user service currently supports looking up users by ID, email, or listing all users. We need a search capability that can find users by partial name matching.

### Requirements

- Add a new method `search_users(self, query: str, skip: int = 0, limit: int = 100) -> List[UserResponse]` to `UserService` in `user-service/services/user_service.py`.
- The search should match against `first_name`, `last_name`, `username`, and `email` fields (case-insensitive partial matching).
- Add a corresponding `search(self, query: str, skip: int = 0, limit: int = 100) -> List[User]` method to `UserRepository` in `user-service/repositories/user_repository.py`.
- Empty or whitespace-only queries should raise a `ValueError`.
- Query must be at least 2 characters long.

### Acceptance Criteria

- [ ] Can search users by partial first name
- [ ] Can search users by partial last name
- [ ] Can search users by partial username
- [ ] Can search users by partial email
- [ ] Search is case-insensitive
- [ ] Empty query raises ValueError
- [ ] Query under 2 characters raises ValueError
- [ ] Results are paginated with skip/limit
- [ ] Unit tests in `user-service/tests/test_user_service.py`

---

## ECOM-108: Add review response feature for sellers in review service

**Project:** review-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

Sellers/merchants should be able to respond to customer reviews. Each review can have at most one seller response.

### Requirements

- Add a `response` attribute (string, initially nil) and `response_at` (Time, initially nil) and `responded_by` (string, initially nil) to the `Review` model in `review-service/models/review.rb`. Update `to_hash` to include these fields.
- Add a method `add_response(review_id, responder_id, response_text)` to `ReviewService` in `review-service/services/review_service.rb`.
- Validate: response_text must be between 10 and 2000 characters, review must exist and be approved, a review can only have one response (raise error if already responded).
- The response should go through the profanity filter.
- Add a method `get_reviews_with_responses(product_id)` that returns only approved reviews that have a seller response.

### Acceptance Criteria

- [ ] Seller can add a response to an approved review
- [ ] Response text is validated for length (10-2000 chars)
- [ ] Response goes through profanity filter
- [ ] Cannot respond to unapproved reviews
- [ ] Cannot add a second response to a review
- [ ] `get_reviews_with_responses` returns correct results
- [ ] Review `to_hash` includes response fields
- [ ] RSpec tests added to `review-service/spec/review_service_spec.rb`

---

## ECOM-109: Add sales comparison period-over-period to analytics service

**Project:** analytics-service
**Type:** Feature
**Priority:** Low
**Status:** To Do

### Description

The analytics service needs a method to compare sales metrics between two time periods (e.g., this month vs. last month) to show growth or decline.

### Requirements

- Add a new method `compare_periods(self, period1_start, period1_end, period2_start, period2_end) -> Dict` to `SalesService` in `analytics-service/analytics_app/services/sales_service.py`.
- The returned dict should include:
  - `period1_total`, `period2_total` - total sales for each period
  - `period1_count`, `period2_count` - transaction count for each period
  - `period1_avg_order`, `period2_avg_order` - average order value per period
  - `revenue_growth_percent` - percentage change from period1 to period2 (use the formula: `((p2 - p1) / p1) * 100`, return 0 if p1 is 0)
  - `order_count_growth_percent` - percentage change in order count
- All date parameters are required; raise `ValueError` if any are None.
- Raise `ValueError` if period1_start > period1_end or period2_start > period2_end.

### Acceptance Criteria

- [ ] Correctly calculates totals for both periods
- [ ] Correctly computes growth percentages
- [ ] Handles zero sales in first period gracefully (0% growth)
- [ ] Validates that all dates are provided
- [ ] Validates that start dates are before end dates
- [ ] Unit tests in `analytics-service/tests/test_sales_service.py`

---

## ECOM-110: Add per-route rate limiting to API gateway

**Project:** api-gateway
**Type:** Feature
**Priority:** High
**Status:** To Do

### Description

The API gateway currently has a single global rate limit applied to all clients. We need to support per-route rate limits so that sensitive endpoints (like `/payments`) can have stricter limits than read-heavy endpoints (like `/products`).

### Requirements

- Add a new method `allow_request_for_route(&mut self, client_id: &str, route_path: &str) -> RateLimitResult` to `RateLimiter` in `api-gateway/src/middleware/rate_limiter.rs`.
- Add a field `route_limits: HashMap<String, u32>` to `RateLimiter` that maps route path prefixes to their requests-per-minute limit.
- Add a method `set_route_limit(&mut self, route_prefix: &str, requests_per_minute: u32)` to configure per-route limits.
- When `allow_request_for_route` is called, it should find the most specific matching route prefix and use its rate limit. If no route-specific limit exists, fall back to the global limit.
- The bucket key should be `"{client_id}:{route_prefix}"` to ensure per-client-per-route tracking.

### Acceptance Criteria

- [ ] Can set per-route rate limits
- [ ] Routes with specific limits use those limits
- [ ] Routes without specific limits use global default
- [ ] Different clients on the same route have independent buckets
- [ ] Same client on different routes has independent buckets
- [ ] Unit tests added in the `#[cfg(test)]` module within `rate_limiter.rs`

---

## ECOM-111: Add bulk product import to product service

**Project:** product-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

The product service needs a bulk import method that can create multiple products at once, returning the results (successes and failures) for each item.

### Requirements

- Add a new method `bulkCreateProducts(products: CreateProductDTO[]): BulkImportResult` to `ProductService` in `product-service/src/services/product.service.ts`.
- Define a new interface `BulkImportResult` in `product-service/src/models/product.model.ts`:
  ```
  interface BulkImportResult {
    successful: Product[];
    failed: Array<{ index: number; sku: string; error: string }>;
    totalProcessed: number;
    successCount: number;
    failureCount: number;
  }
  ```
- Each product should be validated individually. Products that fail validation or have duplicate SKUs should be added to the `failed` array with the error message, while valid products are created and added to `successful`.
- The method should process all products, not stop on the first error.
- Limit bulk import to 100 products per call; throw an error if the array exceeds this.

### Acceptance Criteria

- [ ] Can import multiple valid products at once
- [ ] Invalid products are captured in the failed array with error messages
- [ ] Valid products in the batch are still created even if others fail
- [ ] Duplicate SKUs within the batch are caught
- [ ] Array size limit of 100 is enforced
- [ ] BulkImportResult interface is properly defined
- [ ] Unit tests in `product-service/src/__tests__/product.service.test.ts`

---

## ECOM-112: Add order notes/comments timeline to order service

**Project:** order-service
**Type:** Feature
**Priority:** Low
**Status:** To Do

### Description

The order service should support adding timestamped notes/comments to an order, creating a timeline of activity. This is useful for customer service tracking.

### Requirements

- Create a new `OrderNote.java` class in `order-service/src/main/java/com/ecommerce/order/model/` with fields: `id` (String, UUID), `orderId` (String), `authorId` (String), `content` (String), `type` (enum: `CUSTOMER`, `INTERNAL`, `SYSTEM`), `createdAt` (LocalDateTime).
- Add a method `addNote(String orderId, String authorId, String content, String type)` to `OrderService` that creates and stores notes in an in-memory list within the service.
- Add a method `getOrderNotes(String orderId)` that returns all notes for an order sorted by createdAt ascending.
- Add a method `getOrderNotesByType(String orderId, String type)` to filter notes by type.
- Validate: content must be 1-1000 characters, orderId must reference an existing order, type must be valid.

### Acceptance Criteria

- [ ] Can add notes to an existing order
- [ ] Notes are returned in chronological order
- [ ] Can filter notes by type
- [ ] Content length validation is enforced
- [ ] Cannot add notes to non-existent orders
- [ ] Invalid note type is rejected
- [ ] Unit tests added to `order-service/src/test/java/com/ecommerce/order/service/OrderServiceTest.java`

---

## ECOM-113: Add warehouse transfer history report to inventory service

**Project:** inventory-service
**Type:** Feature
**Priority:** Low
**Status:** To Do

### Description

The `StockService` tracks stock movements but there's no way to get a summary report of movements by warehouse or by type over a time range. Add reporting methods.

### Requirements

- Add the following methods to `StockService` in `inventory-service/services/stock_service.py`:
  - `get_movement_summary(self, warehouse_id: str = None, movement_type: MovementType = None, start_date: datetime = None, end_date: datetime = None) -> dict` that returns:
    - `total_movements`: count of matching movements
    - `total_quantity`: sum of quantities (absolute values)
    - `by_type`: dict of movement_type -> count
    - `by_warehouse`: dict of warehouse_id -> count
  - `get_movement_history(self, warehouse_id: str, limit: int = 50) -> List[StockMovement]` that returns the most recent movements for a warehouse, sorted by `created_at` descending.
- All filters should be optional and composable.

### Acceptance Criteria

- [ ] `get_movement_summary` returns correct counts and totals
- [ ] Filtering by warehouse_id works correctly
- [ ] Filtering by movement_type works correctly
- [ ] Filtering by date range works correctly
- [ ] Filters can be combined
- [ ] `get_movement_history` returns movements sorted by most recent first
- [ ] `get_movement_history` respects the limit parameter
- [ ] Unit tests in `inventory-service/tests/test_stock_service.py`

---

## ECOM-114: Add batch notification sending to notification service

**Project:** notification-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

The notification service currently only sends notifications one at a time. We need a batch send method for scenarios like promotional campaigns where the same notification template needs to be sent to many users.

### Requirements

- Add a new method `async sendBatchNotification({ userIds, channel, subject, body, templateId, metadata, priority })` to `NotificationService` in `notification-service/src/services/notification.service.js`.
- The method sends the same notification to all specified user IDs.
- Returns a batch result object: `{ total, successCount, failureCount, results: [{userId, notificationId, status}] }`.
- Each notification is sent independently; one failure should not stop the others.
- Limit batch size to 500 user IDs; throw an error if exceeded.
- Empty `userIds` array should throw an error.

### Acceptance Criteria

- [ ] Can send same notification to multiple users
- [ ] Returns accurate success/failure counts
- [ ] Individual failures don't block other sends
- [ ] Batch size limit of 500 is enforced
- [ ] Empty userIds array throws error
- [ ] Each send creates its own Notification record and delivery log
- [ ] Unit tests in `notification-service/src/__tests__/notification.service.test.js`

---

## ECOM-115: Add shipping insurance option to shipping service

**Project:** shipping-service
**Type:** Feature
**Priority:** Low
**Status:** To Do

### Description

The shipping service should support an optional shipping insurance add-on for high-value packages. The insurance cost is calculated as a percentage of the declared package value.

### Requirements

- Add a new `InsuranceOption` struct in `shipping-service/models/rate.go` with fields: `Available bool`, `Cost float64`, `Coverage float64`, `Provider string`.
- Add an `Insurance *InsuranceOption` field to the existing `ShippingRate` struct.
- Add a method `CalculateInsurance(declaredValue float64, carrierCode string) (*InsuranceOption, error)` to `RateCalculator` in `shipping-service/services/rate_calculator.go`.
- Insurance rates: 2% of declared value for FedEx, 2.5% for UPS, 1.8% for USPS. Minimum insurance cost is $1.50. Maximum coverage is $5000.
- Return error if declared value is <= 0 or > max coverage.
- Add a method `GetRatesWithInsurance(req RateRequest, declaredValue float64) ([]ShippingRate, error)` that returns all rates with insurance options populated.

### Acceptance Criteria

- [ ] Insurance cost is correctly calculated per carrier
- [ ] Minimum cost of $1.50 is enforced
- [ ] Maximum coverage of $5000 is enforced
- [ ] Invalid declared values return errors
- [ ] `GetRatesWithInsurance` populates insurance on each rate
- [ ] Unit tests in `shipping-service/services/rate_calculator_test.go`

---

## ECOM-116: Add customer lifetime value calculation to analytics service

**Project:** analytics-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

Add a Customer Lifetime Value (CLV) calculation method to the customer analytics service to help identify high-value customers and predict future revenue.

### Requirements

- Add the following methods to `CustomerAnalyticsService` in `analytics-service/analytics_app/services/customer_service.py`:
  - `calculate_clv(self, customer_id: str, avg_lifespan_months: int = 24) -> dict` that returns:
    - `customer_id`: the customer ID
    - `total_revenue`: total amount from purchase events
    - `purchase_count`: number of purchases
    - `avg_purchase_value`: average purchase amount
    - `purchase_frequency`: purchases per month since first purchase
    - `estimated_clv`: calculated as `avg_purchase_value * purchase_frequency * avg_lifespan_months`
  - `get_clv_segments(self, avg_lifespan_months: int = 24) -> dict` that returns a dict with keys `"high"` (CLV > 1000), `"medium"` (CLV 200-1000), `"low"` (CLV < 200), each containing a list of `{customer_id, estimated_clv}`.
- If a customer has no purchase events, `estimated_clv` should be 0.
- `avg_lifespan_months` must be positive; raise ValueError otherwise.

### Acceptance Criteria

- [ ] CLV is correctly calculated based on purchase history
- [ ] Handles customers with no purchases (returns 0)
- [ ] Purchase frequency is calculated relative to first purchase date
- [ ] CLV segments correctly categorize customers
- [ ] Invalid lifespan parameter raises ValueError
- [ ] Unit tests in `analytics-service/tests/test_customer_service.py`

---

## ECOM-117: Add user role management to user service

**Project:** user-service
**Type:** Feature
**Priority:** High
**Status:** To Do

### Description

The user service currently has no concept of user roles. We need to add role management to support different permission levels (e.g., customer, seller, admin).

### Requirements

- Add a `role` field (string, default `"customer"`) to the `User` model in `user-service/models/user.py`. Valid roles are: `"customer"`, `"seller"`, `"admin"`, `"support"`.
- Add the `role` field to `UserResponse` and `UserCreate` (optional in UserCreate, default `"customer"`).
- Add a method `change_role(self, user_id: str, new_role: str) -> Optional[UserResponse]` to `UserService` in `user-service/services/user_service.py`.
- Validate that the role is one of the allowed values; raise `ValueError` for invalid roles.
- Add a method `list_users_by_role(self, role: str) -> List[UserResponse]` that returns all users with a specific role.
- Add a `find_by_role(self, role: str) -> List[User]` method to `UserRepository` in `user-service/repositories/user_repository.py`.

### Acceptance Criteria

- [ ] New users default to "customer" role
- [ ] Can change a user's role to any valid role
- [ ] Invalid role values raise ValueError
- [ ] Can list all users with a specific role
- [ ] UserResponse includes the role field
- [ ] Unit tests in `user-service/tests/test_user_service.py`

---

## ECOM-118: Add review photo attachments support to review service

**Project:** review-service
**Type:** Feature
**Priority:** Low
**Status:** To Do

### Description

Allow customers to attach photo URLs to their reviews when creating or updating them. This helps other customers make purchasing decisions.

### Requirements

- Add a `photos` attribute (array of strings, initially empty) to the `Review` model in `review-service/models/review.rb`. Each string is a URL. Update `to_hash` to include this field.
- Allow passing `photos` (array) during `create_review` and `update_review` in `ReviewService`.
- Add validation: maximum 5 photos per review, each URL must start with `http://` or `https://`, and each URL must be under 500 characters.
- Add a method `get_reviews_with_photos(product_id)` that returns approved reviews that have at least one photo.
- Add validation in `ReviewValidator` in `review-service/validators/review_validator.rb`: add a `validate_photos!(photos)` method.

### Acceptance Criteria

- [ ] Reviews can be created with photo URLs
- [ ] Maximum of 5 photos enforced
- [ ] Invalid URLs are rejected
- [ ] URLs over 500 chars are rejected
- [ ] `get_reviews_with_photos` returns correct subset
- [ ] Photos are included in `to_hash` output
- [ ] RSpec tests in `review-service/spec/review_service_spec.rb`

---

## ECOM-119: Add payment retry with exponential backoff to payment service

**Project:** payment-service
**Type:** Feature
**Priority:** Medium
**Status:** To Do

### Description

When a payment processing attempt fails, the system should support retrying with configurable exponential backoff. Currently, there is no retry mechanism.

### Requirements

- Add a `RetryCount` field (int) and `MaxRetries` field (int, default 3) and `LastError` field (string) to the `Payment` struct in `payment-service/models/payment.go`.
- Add a new method `RetryPayment(paymentID string) (*Payment, error)` to `PaymentService` in `payment-service/services/payment_service.go`.
- The method should:
  1. Only retry payments in `failed` status
  2. Check that `RetryCount < MaxRetries`
  3. Calculate backoff delay: `2^retryCount` seconds (for the purpose of this mock, just record it in the payment metadata, don't actually wait)
  4. Increment `RetryCount`
  5. Attempt to process the payment again (reuse `ProcessPayment` logic)
  6. If it fails again, update `LastError` and keep status as `failed`
- Add a method `GetRetryablePayments() ([]*Payment, error)` that returns all failed payments that haven't exceeded max retries.
- Add a new `PaymentStatusFailed` constant to the payment status types.

### Acceptance Criteria

- [ ] Can retry a failed payment
- [ ] RetryCount is incremented on each attempt
- [ ] Cannot retry payments that aren't in failed status
- [ ] Cannot retry payments that exceeded max retries
- [ ] `GetRetryablePayments` returns correct list
- [ ] Backoff delay is calculated and recorded in metadata
- [ ] Unit tests in `payment-service/services/payment_service_test.go`

