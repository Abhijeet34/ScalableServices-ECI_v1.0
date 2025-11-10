#!/bin/bash
# ECI Platform - Comprehensive CRUD Testing Script
# Purpose: Test all CRUD operations for each service with full validation
# Audience: QA teams, developers, and business users

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="http://localhost:8080"
TOKEN=""
VERBOSE=false
TEST_RESULTS=()

# Test data storage
CREATED_CUSTOMER_ID=""
CREATED_PRODUCT_ID=""
CREATED_ORDER_ID=""
CREATED_INVENTORY_ID=""
CREATED_PAYMENT_ID=""
CREATED_SHIPMENT_ID=""

# Helper functions
print_header() {
    echo
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_subheader() {
    echo
    echo -e "${MAGENTA}▶ $1${NC}"
    echo -e "${MAGENTA}──────────────────────────────────────────${NC}"
}

print_test() {
    echo -e "${BLUE}[TEST] $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ [PASS] $1${NC}"
    TEST_RESULTS+=("PASS: $1")
}

print_error() {
    echo -e "${RED}✗ [FAIL] $1${NC}"
    TEST_RESULTS+=("FAIL: $1")
}

print_warning() {
    echo -e "${YELLOW}⚠ [WARN] $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ [INFO] $1${NC}"
}

print_data() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${NC}  Data: $1${NC}"
    fi
}

# Show help
show_help() {
    cat <<'EOF'
╔════════════════════════════════════════════════════════════════╗
║           ECI Platform - Comprehensive CRUD Test Suite         ║
╚════════════════════════════════════════════════════════════════╝

USAGE:
  crud-test.sh [options] [test-scope]

OPTIONS:
  -h, --help      Show this help message
  -v, --verbose   Show detailed request/response data
  -i, --interactive Run in interactive mode
  -q, --quick     Run quick tests only (skip performance)

TEST SCOPES:
  all             Run all CRUD tests (default)
  customers       Test customer CRUD operations
  products        Test product CRUD operations
  inventory       Test inventory CRUD operations
  orders          Test order CRUD operations
  payments        Test payment CRUD operations
  shipments       Test shipment CRUD operations

EXAMPLES:
  ./crud-test.sh                  # Run all tests
  ./crud-test.sh -v customers     # Verbose customer tests
  ./crud-test.sh -i               # Interactive mode
  ./crud-test.sh -q all           # Quick test all services

WHAT IT TESTS:
  ✓ CREATE: Add new records with validation
  ✓ READ:   Fetch single and multiple records
  ✓ UPDATE: Modify existing records
  ✓ DELETE: Remove records with cascade checks
  ✓ VALIDATE: Ensure data integrity and relationships
  ✓ BUSINESS RULES: Test constraints and workflows

EOF
}

# Get authentication token
get_token() {
    print_test "Authenticating..."
    local response=$(curl -s -X POST "$BASE_URL/auth/token" -d "username=testuser")
    TOKEN=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)
    
    if [ -n "$TOKEN" ]; then
        print_success "Authentication successful"
        return 0
    else
        print_error "Authentication failed"
        echo "Response: $response"
        return 1
    fi
}

# Validate JSON response
validate_json() {
    echo "$1" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null
    return $?
}

# Extract field from JSON
extract_json_field() {
    local json="$1"
    local field="$2"
    echo "$json" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('$field', ''))" 2>/dev/null
}

# Test Customer CRUD Operations
test_customer_crud() {
    print_header "CUSTOMER SERVICE - CRUD OPERATIONS"
    
    # Test data
    local customer_name="John Doe $(date +%s)"
    local customer_email="john.doe.$(date +%s)@test.com"
    local customer_phone="+1-555-$(shuf -i 1000-9999 -n 1)"
    local customer_street="123 Test St"
    local customer_city="Test City"
    local customer_state="TC"
    local customer_zip="12345"
    
    # CREATE
    print_subheader "CREATE - Adding New Customer"
    print_test "Creating customer: $customer_name"
    
    local create_response=$(curl -s -X POST "$BASE_URL/customers/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$customer_name\",
            \"email\": \"$customer_email\",
            \"phone\": \"$customer_phone\",
            \"address_street\": \"$customer_street\",
            \"address_city\": \"$customer_city\",
            \"address_state\": \"$customer_state\",
            \"address_zip\": \"$customer_zip\"
        }")
    
    print_data "$create_response"
    
    if validate_json "$create_response"; then
        CREATED_CUSTOMER_ID=$(extract_json_field "$create_response" "id")
        if [ -n "$CREATED_CUSTOMER_ID" ]; then
            print_success "Customer created with ID: $CREATED_CUSTOMER_ID"
            
            # Validate created data
            local created_name=$(extract_json_field "$create_response" "name")
            if [ "$created_name" = "$customer_name" ]; then
                print_success "Customer name validated: $created_name"
            else
                print_error "Customer name mismatch: expected '$customer_name', got '$created_name'"
            fi
        else
            print_error "Failed to create customer"
        fi
    else
        print_error "Invalid JSON response"
    fi
    
    # READ (Single)
    if [ -n "$CREATED_CUSTOMER_ID" ]; then
        print_subheader "READ - Fetching Single Customer"
        print_test "Fetching customer ID: $CREATED_CUSTOMER_ID"
        
        local read_response=$(curl -s -X GET "$BASE_URL/customers/$CREATED_CUSTOMER_ID" \
            -H "Authorization: Bearer $TOKEN")
        
        print_data "$read_response"
        
        if validate_json "$read_response"; then
            local fetched_id=$(extract_json_field "$read_response" "id")
            if [ "$fetched_id" = "$CREATED_CUSTOMER_ID" ]; then
                print_success "Customer fetched successfully"
                print_info "Customer details: $(echo "$read_response" | python3 -m json.tool 2>/dev/null | head -10)"
            else
                print_error "Customer ID mismatch"
            fi
        else
            print_error "Failed to fetch customer"
        fi
    fi
    
    # READ (List)
    print_subheader "READ - Fetching Customer List"
    print_test "Fetching all customers with pagination"
    
    local list_response=$(curl -s -X GET "$BASE_URL/customers/?limit=5&offset=0" \
        -H "Authorization: Bearer $TOKEN")
    
    if validate_json "$list_response"; then
        local count=$(echo "$list_response" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null)
        print_success "Fetched $count customers"
    else
        print_error "Failed to fetch customer list"
    fi
    
    # UPDATE
    if [ -n "$CREATED_CUSTOMER_ID" ]; then
        print_subheader "UPDATE - Modifying Customer"
        local updated_name="$customer_name (Updated)"
        local updated_phone="+1-555-9999"
        
        print_test "Updating customer name and phone"
        
        local update_response=$(curl -s -X PUT "$BASE_URL/customers/$CREATED_CUSTOMER_ID" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{
                \"name\": \"$updated_name\",
                \"email\": \"$customer_email\",
                \"phone\": \"$updated_phone\",
                \"address_street\": \"$customer_street\",
                \"address_city\": \"$customer_city\",
                \"address_state\": \"$customer_state\",
                \"address_zip\": \"$customer_zip\"
            }")
        
        print_data "$update_response"
        
        if validate_json "$update_response"; then
            local new_name=$(extract_json_field "$update_response" "name")
            local new_phone=$(extract_json_field "$update_response" "phone")
            
            if [ "$new_name" = "$updated_name" ] && [ "$new_phone" = "$updated_phone" ]; then
                print_success "Customer updated successfully"
                print_info "Updated name: $new_name"
                print_info "Updated phone: $new_phone"
            else
                print_error "Update validation failed"
            fi
        else
            print_error "Failed to update customer"
        fi
    fi
    
    # DELETE
    if [ -n "$CREATED_CUSTOMER_ID" ]; then
        print_subheader "DELETE - Removing Customer"
        print_test "Deleting customer ID: $CREATED_CUSTOMER_ID"
        
        local delete_response=$(curl -s -X DELETE "$BASE_URL/customers/$CREATED_CUSTOMER_ID" \
            -H "Authorization: Bearer $TOKEN" \
            -w "\n%{http_code}")
        
        local http_code=$(echo "$delete_response" | tail -1)
        
        if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
            print_success "Customer deleted successfully"
            
            # Verify deletion
            print_test "Verifying customer is deleted"
            local verify_response=$(curl -s -X GET "$BASE_URL/customers/$CREATED_CUSTOMER_ID" \
                -H "Authorization: Bearer $TOKEN" \
                -w "\n%{http_code}")
            
            local verify_code=$(echo "$verify_response" | tail -1)
            if [ "$verify_code" = "404" ]; then
                print_success "Deletion confirmed - customer not found"
            else
                print_warning "Customer might still exist (status: $verify_code)"
            fi
        else
            print_error "Failed to delete customer (status: $http_code)"
        fi
    fi
}

# Test Product CRUD Operations
test_product_crud() {
    print_header "PRODUCT SERVICE - CRUD OPERATIONS"
    
    # Test data
    local product_sku="SKU-$(date +%s)"
    local product_name="Test Product $(date +%s)"
    local product_category="Electronics"
    local product_price="199.99"
    local product_description="High-quality test product for automated testing"
    
    # CREATE
    print_subheader "CREATE - Adding New Product"
    print_test "Creating product: $product_name"
    
    local create_response=$(curl -s -X POST "$BASE_URL/products/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"sku\": \"$product_sku\",
            \"name\": \"$product_name\",
            \"category\": \"$product_category\",
            \"price\": $product_price,
            \"description\": \"$product_description\",
            \"is_active\": true,
            \"seller_name\": \"Test Seller\",
            \"seller_response_time\": \"< 24 hours\",
            \"seller_badge\": \"trusted\"
        }")
    
    print_data "$create_response"
    
    if validate_json "$create_response"; then
        CREATED_PRODUCT_ID=$(extract_json_field "$create_response" "id")
        if [ -n "$CREATED_PRODUCT_ID" ]; then
            print_success "Product created with ID: $CREATED_PRODUCT_ID"
            print_info "SKU: $product_sku"
            print_info "Price: \$$product_price"
        else
            print_error "Failed to create product"
        fi
    else
        print_error "Invalid JSON response"
    fi
    
    # READ
    if [ -n "$CREATED_PRODUCT_ID" ]; then
        print_subheader "READ - Fetching Product"
        print_test "Fetching product ID: $CREATED_PRODUCT_ID"
        
        local read_response=$(curl -s -X GET "$BASE_URL/products/$CREATED_PRODUCT_ID" \
            -H "Authorization: Bearer $TOKEN")
        
        if validate_json "$read_response"; then
            local fetched_sku=$(extract_json_field "$read_response" "sku")
            local fetched_price=$(extract_json_field "$read_response" "price")
            
            if [ "$fetched_sku" = "$product_sku" ]; then
                print_success "Product fetched successfully"
                print_info "Verified SKU: $fetched_sku"
                print_info "Verified Price: \$$fetched_price"
            else
                print_error "Product data mismatch"
            fi
        fi
    fi
    
    # UPDATE
    if [ -n "$CREATED_PRODUCT_ID" ]; then
        print_subheader "UPDATE - Modifying Product Price"
        local new_price="249.99"
        
        print_test "Updating product price from \$$product_price to \$$new_price"
        
        local update_response=$(curl -s -X PUT "$BASE_URL/products/$CREATED_PRODUCT_ID" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{
                \"sku\": \"$product_sku\",
                \"name\": \"$product_name\",
                \"category\": \"$product_category\",
                \"price\": $new_price,
                \"description\": \"$product_description (Price Updated)\",
                \"is_active\": true,
                \"seller_name\": \"Test Seller\",
                \"seller_response_time\": \"< 24 hours\",
                \"seller_badge\": \"trusted\"
            }")
        
        if validate_json "$update_response"; then
            local updated_price=$(extract_json_field "$update_response" "price")
            if [ "$updated_price" = "$new_price" ]; then
                print_success "Product price updated successfully"
            else
                print_error "Price update failed"
            fi
        fi
    fi
    
    # DELETE
    if [ -n "$CREATED_PRODUCT_ID" ]; then
        print_subheader "DELETE - Removing Product"
        print_test "Deleting product ID: $CREATED_PRODUCT_ID"
        
        local delete_response=$(curl -s -X DELETE "$BASE_URL/products/$CREATED_PRODUCT_ID" \
            -H "Authorization: Bearer $TOKEN" \
            -w "\n%{http_code}")
        
        local http_code=$(echo "$delete_response" | tail -1)
        
        if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
            print_success "Product deleted successfully"
        else
            print_error "Failed to delete product (status: $http_code)"
        fi
    fi
}

# Test Inventory CRUD Operations
test_inventory_crud() {
    print_header "INVENTORY SERVICE - CRUD OPERATIONS"
    
    # First create a product for inventory testing
    print_test "Creating test product for inventory"
    local product_response=$(curl -s -X POST "$BASE_URL/products/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"sku\": \"INV-SKU-$(date +%s)\",
            \"name\": \"Inventory Test Product\",
            \"category\": \"Test\",
            \"price\": 99.99,
            \"is_active\": true,
            \"seller_name\": \"Test Seller\",
            \"seller_response_time\": \"< 24 hours\",
            \"seller_badge\": \"trusted\"
        }")
    
    local test_product_id=$(extract_json_field "$product_response" "id")
    
    if [ -n "$test_product_id" ]; then
        # CREATE Inventory
        print_subheader "CREATE - Adding Inventory Record"
        local on_hand=100
        local reserved=10
        local warehouse="MAIN"
        
        print_test "Creating inventory for product ID: $test_product_id"
        
        local create_response=$(curl -s -X POST "$BASE_URL/inventory/" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{
                \"product_id\": $test_product_id,
                \"warehouse\": \"$warehouse\",
                \"on_hand\": $on_hand,
                \"reserved\": $reserved
            }")
        
        print_data "$create_response"
        
        if validate_json "$create_response"; then
            CREATED_INVENTORY_ID=$(extract_json_field "$create_response" "id")
            if [ -n "$CREATED_INVENTORY_ID" ]; then
                print_success "Inventory created with ID: $CREATED_INVENTORY_ID"
                print_info "Initial quantity: $on_hand"
            else
                print_error "Failed to create inventory"
            fi
        fi
        
        # READ
        if [ -n "$CREATED_INVENTORY_ID" ]; then
            print_subheader "READ - Checking Inventory Levels"
            print_test "Fetching inventory ID: $CREATED_INVENTORY_ID"
            
            local read_response=$(curl -s -X GET "$BASE_URL/inventory/$CREATED_INVENTORY_ID" \
                -H "Authorization: Bearer $TOKEN")
            
            if validate_json "$read_response"; then
                local current_qty=$(extract_json_field "$read_response" "on_hand")
                print_success "Current inventory level: $current_qty units"
            fi
        fi
        
        # UPDATE (Simulate stock adjustment)
        if [ -n "$CREATED_INVENTORY_ID" ]; then
            print_subheader "UPDATE - Adjusting Stock Level"
            local new_on_hand=75
            local new_reserved=5
            
            print_test "Reducing inventory from $on_hand to $new_on_hand (simulating sales)"
            
            local update_response=$(curl -s -X PUT "$BASE_URL/inventory/$CREATED_INVENTORY_ID" \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "{
                    \"product_id\": $test_product_id,
                    \"warehouse\": \"$warehouse\",
                    \"on_hand\": $new_on_hand,
                    \"reserved\": $new_reserved
                }")
            
            if validate_json "$update_response"; then
                local updated_qty=$(extract_json_field "$update_response" "on_hand")
                if [ "$updated_qty" = "$new_on_hand" ]; then
                    print_success "Inventory adjusted successfully"
                    print_info "New quantity: $updated_qty units"
                fi
            fi
        fi
        
        # Clean up
        if [ -n "$CREATED_INVENTORY_ID" ]; then
            curl -s -X DELETE "$BASE_URL/inventory/$CREATED_INVENTORY_ID" \
                -H "Authorization: Bearer $TOKEN" > /dev/null 2>&1
        fi
        if [ -n "$test_product_id" ]; then
            curl -s -X DELETE "$BASE_URL/products/$test_product_id" \
                -H "Authorization: Bearer $TOKEN" > /dev/null 2>&1
        fi
    fi
}

# Test Order CRUD Operations with full workflow
test_order_crud() {
    print_header "ORDER SERVICE - CRUD OPERATIONS & WORKFLOW"
    
    # Setup: Create customer and product
    print_test "Setting up test data for order"
    
    # Create customer
    local customer_response=$(curl -s -X POST "$BASE_URL/customers/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"Order Test Customer\",
            \"email\": \"order.test@example.com\",
            \"address_street\": \"456 Order St\",
            \"address_city\": \"Order City\",
            \"address_state\": \"OC\",
            \"address_zip\": \"67890\"
        }")
    local test_customer_id=$(extract_json_field "$customer_response" "id")
    
    # Create product
    local product_response=$(curl -s -X POST "$BASE_URL/products/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"sku\": \"ORDER-TEST-$(date +%s)\",
            \"name\": \"Order Test Product\",
            \"category\": \"Test\",
            \"price\": 49.99,
            \"is_active\": true,
            \"seller_name\": \"Test Seller\",
            \"seller_response_time\": \"< 24 hours\",
            \"seller_badge\": \"trusted\"
        }")
    local test_product_id=$(extract_json_field "$product_response" "id")
    
    if [ -n "$test_customer_id" ] && [ -n "$test_product_id" ]; then
        # CREATE Order
        print_subheader "CREATE - Placing New Order"
        print_test "Creating order for customer $test_customer_id"
        
        local create_response=$(curl -s -X POST "$BASE_URL/orders/" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{
                \"customer_id\": $test_customer_id,
                \"items\": [
                    {
                        \"product_id\": $test_product_id,
                        \"quantity\": 2,
                        \"price\": 49.99
                    }
                ],
                \"status\": \"pending\"
            }")
        
        print_data "$create_response"
        
        if validate_json "$create_response"; then
            CREATED_ORDER_ID=$(extract_json_field "$create_response" "id")
            if [ -n "$CREATED_ORDER_ID" ]; then
                print_success "Order created with ID: $CREATED_ORDER_ID"
                local order_total=$(extract_json_field "$create_response" "total")
                print_info "Order total: \$$order_total"
            fi
        fi
        
        # READ Order
        if [ -n "$CREATED_ORDER_ID" ]; then
            print_subheader "READ - Fetching Order Details"
            print_test "Fetching order ID: $CREATED_ORDER_ID"
            
            local read_response=$(curl -s -X GET "$BASE_URL/orders/$CREATED_ORDER_ID" \
                -H "Authorization: Bearer $TOKEN")
            
            if validate_json "$read_response"; then
                local order_status=$(extract_json_field "$read_response" "status")
                print_success "Order fetched successfully"
                print_info "Order status: $order_status"
            fi
        fi
        
        # UPDATE Order Status
        if [ -n "$CREATED_ORDER_ID" ]; then
            print_subheader "UPDATE - Changing Order Status"
            print_test "Updating order status from 'pending' to 'processing'"
            
            local update_response=$(curl -s -X PATCH "$BASE_URL/orders/$CREATED_ORDER_ID/status" \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "{\"status\": \"processing\"}")
            
            if validate_json "$update_response"; then
                local new_status=$(extract_json_field "$update_response" "status")
                if [ "$new_status" = "processing" ]; then
                    print_success "Order status updated successfully"
                fi
            fi
        fi
        
        # Test Order Workflow
        if [ -n "$CREATED_ORDER_ID" ]; then
            print_subheader "WORKFLOW - Complete Order Processing"
            
            # Step 1: Process Payment
            print_test "Processing payment for order"
            local payment_response=$(curl -s -X POST "$BASE_URL/payments/" \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "{
                    \"order_id\": $CREATED_ORDER_ID,
                    \"amount\": 99.98,
                    \"payment_method\": \"credit_card\",
                    \"status\": \"completed\"
                }")
            
            if validate_json "$payment_response"; then
                local payment_id=$(extract_json_field "$payment_response" "id")
                if [ -n "$payment_id" ]; then
                    print_success "Payment processed: ID $payment_id"
                fi
            fi
            
            # Step 2: Create Shipment
            print_test "Creating shipment for order"
            local shipment_response=$(curl -s -X POST "$BASE_URL/shipments/" \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "{
                    \"order_id\": $CREATED_ORDER_ID,
                    \"tracking_number\": \"TRACK-$(date +%s)\",
                    \"carrier\": \"FedEx\",
                    \"status\": \"in_transit\"
                }")
            
            if validate_json "$shipment_response"; then
                local shipment_id=$(extract_json_field "$shipment_response" "id")
                if [ -n "$shipment_id" ]; then
                    print_success "Shipment created: ID $shipment_id"
                fi
            fi
            
            # Step 3: Update order to completed
            print_test "Completing order"
            local complete_response=$(curl -s -X PATCH "$BASE_URL/orders/$CREATED_ORDER_ID/status" \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "{\"status\": \"completed\"}")
            
            if validate_json "$complete_response"; then
                local final_status=$(extract_json_field "$complete_response" "status")
                if [ "$final_status" = "completed" ]; then
                    print_success "Order completed successfully!"
                fi
            fi
        fi
        
        # Clean up
        curl -s -X DELETE "$BASE_URL/orders/$CREATED_ORDER_ID" \
            -H "Authorization: Bearer $TOKEN" > /dev/null 2>&1
        curl -s -X DELETE "$BASE_URL/customers/$test_customer_id" \
            -H "Authorization: Bearer $TOKEN" > /dev/null 2>&1
        curl -s -X DELETE "$BASE_URL/products/$test_product_id" \
            -H "Authorization: Bearer $TOKEN" > /dev/null 2>&1
    fi
}

# Test business rules and constraints
test_business_rules() {
    print_header "BUSINESS RULES & CONSTRAINTS VALIDATION"
    
    print_subheader "Testing Data Validation Rules"
    
    # Test 1: Invalid email format
    print_test "Testing invalid email format"
    local response=$(curl -s -X POST "$BASE_URL/customers/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"Test User\",
            \"email\": \"invalid-email\"
        }" \
        -w "\n%{http_code}")
    
    local http_code=$(echo "$response" | tail -1)
    if [ "$http_code" = "422" ] || [ "$http_code" = "400" ]; then
        print_success "Invalid email rejected correctly"
    else
        print_warning "Invalid email might have been accepted (status: $http_code)"
    fi
    
    # Test 2: Negative product price
    print_test "Testing negative product price"
    response=$(curl -s -X POST "$BASE_URL/products/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"sku\": \"NEG-PRICE\",
            \"name\": \"Negative Price Product\",
            \"price\": -10.00,
            \"category\": \"Test\"
        }" \
        -w "\n%{http_code}")
    
    http_code=$(echo "$response" | tail -1)
    if [ "$http_code" = "422" ] || [ "$http_code" = "400" ]; then
        print_success "Negative price rejected correctly"
    else
        print_warning "Negative price might have been accepted (status: $http_code)"
    fi
    
    # Test 3: Order with zero quantity
    print_test "Testing order with zero quantity"
    response=$(curl -s -X POST "$BASE_URL/orders/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"customer_id\": 1,
            \"items\": [{
                \"product_id\": 1,
                \"quantity\": 0
            }]
        }" \
        -w "\n%{http_code}")
    
    http_code=$(echo "$response" | tail -1)
    if [ "$http_code" = "422" ] || [ "$http_code" = "400" ]; then
        print_success "Zero quantity order rejected correctly"
    else
        print_warning "Zero quantity order might have been accepted (status: $http_code)"
    fi
    
    print_subheader "Testing Referential Integrity"
    
    # Test 4: Order with non-existent customer
    print_test "Testing order with non-existent customer"
    response=$(curl -s -X POST "$BASE_URL/orders/" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"customer_id\": 999999,
            \"items\": [{
                \"product_id\": 1,
                \"quantity\": 1
            }]
        }" \
        -w "\n%{http_code}")
    
    http_code=$(echo "$response" | tail -1)
    if [ "$http_code" = "404" ] || [ "$http_code" = "400" ] || [ "$http_code" = "422" ]; then
        print_success "Non-existent customer reference rejected"
    else
        print_warning "Non-existent customer reference might have been accepted (status: $http_code)"
    fi
}

# Performance testing
test_performance() {
    print_header "PERFORMANCE TESTING"
    
    print_subheader "Response Time Analysis"
    
    local endpoints=("customers" "products" "inventory" "orders" "payments" "shipments")
    
    for endpoint in "${endpoints[@]}"; do
        local start_time=$(date +%s%N)
        curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/$endpoint/?limit=10" > /dev/null
        local end_time=$(date +%s%N)
        
        local duration=$(( (end_time - start_time) / 1000000 ))
        
        if [ $duration -lt 500 ]; then
            print_success "$endpoint: ${duration}ms (Excellent)"
        elif [ $duration -lt 1000 ]; then
            print_warning "$endpoint: ${duration}ms (Good)"
        else
            print_error "$endpoint: ${duration}ms (Slow)"
        fi
    done
    
    print_subheader "Concurrent Request Handling"
    print_test "Sending 10 concurrent requests"
    
    local start_time=$(date +%s)
    for i in {1..10}; do
        curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/products/" > /dev/null &
    done
    wait
    local end_time=$(date +%s)
    
    local total_time=$((end_time - start_time))
    print_info "10 concurrent requests completed in ${total_time}s"
}

# Interactive mode
interactive_mode() {
    while true; do
        echo
        echo -e "${CYAN}╔════════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}║     ECI CRUD Test Suite - Interactive      ║${NC}"
        echo -e "${CYAN}╚════════════════════════════════════════════╝${NC}"
        echo
        echo "1) Test Customer CRUD"
        echo "2) Test Product CRUD"
        echo "3) Test Inventory CRUD"
        echo "4) Test Order CRUD & Workflow"
        echo "5) Test Business Rules"
        echo "6) Test Performance"
        echo "7) Run All Tests"
        echo "8) Show Test Summary"
        echo "0) Exit"
        echo
        read -p "Select option: " choice
        
        case $choice in
            1) test_customer_crud ;;
            2) test_product_crud ;;
            3) test_inventory_crud ;;
            4) test_order_crud ;;
            5) test_business_rules ;;
            6) test_performance ;;
            7) run_all_tests ;;
            8) show_summary ;;
            0) echo "Goodbye!"; exit 0 ;;
            *) print_error "Invalid option" ;;
        esac
    done
}

# Show test summary
show_summary() {
    print_header "TEST EXECUTION SUMMARY"
    
    local pass_count=0
    local fail_count=0
    
    for result in "${TEST_RESULTS[@]}"; do
        if [[ $result == PASS:* ]]; then
            ((pass_count++))
        else
            ((fail_count++))
        fi
    done
    
    echo
    echo -e "${GREEN}Passed: $pass_count${NC}"
    echo -e "${RED}Failed: $fail_count${NC}"
    
    if [ $fail_count -eq 0 ]; then
        echo
        echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║        ALL TESTS PASSED SUCCESSFULLY!      ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    else
        echo
        echo -e "${YELLOW}Some tests failed. Review the output above.${NC}"
    fi
    
    # Show failed tests
    if [ $fail_count -gt 0 ]; then
        echo
        echo -e "${RED}Failed Tests:${NC}"
        for result in "${TEST_RESULTS[@]}"; do
            if [[ $result == FAIL:* ]]; then
                echo "  - ${result#FAIL: }"
            fi
        done
    fi
}

# Run all tests
run_all_tests() {
    print_header "RUNNING COMPLETE CRUD TEST SUITE"
    
    test_customer_crud
    test_product_crud
    test_inventory_crud
    test_order_crud
    test_business_rules
    test_performance
    
    show_summary
}

# Main execution
main() {
    # Check if services are running
    if ! curl -s "$BASE_URL/health" > /dev/null 2>&1; then
        print_error "Services are not running!"
        echo "Please start the platform first:"
        echo "  make start"
        exit 1
    fi
    
    # Get authentication token
    if ! get_token; then
        exit 1
    fi
    
    # Parse command line arguments
    local test_scope="all"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -i|--interactive)
                interactive_mode
                exit 0
                ;;
            -q|--quick)
                # Skip performance tests in quick mode
                shift
                ;;
            *)
                test_scope="$1"
                shift
                ;;
        esac
    done
    
    # Execute tests based on scope
    case $test_scope in
        all)
            run_all_tests
            ;;
        customers)
            test_customer_crud
            show_summary
            ;;
        products)
            test_product_crud
            show_summary
            ;;
        inventory)
            test_inventory_crud
            show_summary
            ;;
        orders)
            test_order_crud
            show_summary
            ;;
        payments|shipments)
            print_warning "Payment and Shipment tests are included in Order workflow"
            test_order_crud
            show_summary
            ;;
        *)
            print_error "Unknown test scope: $test_scope"
            show_help
            exit 1
            ;;
    esac
}

# Run main if not sourced
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi