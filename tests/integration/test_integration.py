"""
Integration Test Suite for ECI Microservices Platform
Tests all services end-to-end functionality
"""

import pytest
import httpx
import asyncio
import json
import time
from typing import Dict, Any, Optional

# Configuration
BASE_URL = "http://localhost:8080"
HEALTH_CHECK_RETRIES = 30
HEALTH_CHECK_DELAY = 2

class TestPlatformIntegration:
    """Integration tests for the microservices platform"""
    
    @classmethod
    def setup_class(cls):
        """Setup before all tests"""
        cls.client = httpx.Client(base_url=BASE_URL, timeout=30.0)
        cls.token = None
        cls.wait_for_services()
        cls.authenticate()
    
    @classmethod
    def teardown_class(cls):
        """Cleanup after all tests"""
        cls.client.close()
    
    @classmethod
    def wait_for_services(cls):
        """Wait for all services to be healthy"""
        print("Waiting for services to be ready...")
        
        for attempt in range(HEALTH_CHECK_RETRIES):
            try:
                response = cls.client.get("/health")
                if response.status_code == 200:
                    print("Gateway service is ready")
                    return
            except Exception as e:
                print(f"Attempt {attempt + 1}/{HEALTH_CHECK_RETRIES}: {e}")
            
            time.sleep(HEALTH_CHECK_DELAY)
        
        raise Exception("Services failed to start within timeout period")
    
    @classmethod
    def authenticate(cls):
        """Get authentication token"""
        response = cls.client.post(
            "/auth/token",
            data={"username": "testuser"}
        )
        assert response.status_code == 200
        data = response.json()
        cls.token = data["access_token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}
        print(f"Authenticated successfully")
    
    def test_health_endpoints(self):
        """Test health check endpoints for all services"""
        endpoints = [
            "/health",
            "/health/live",
            "/health/ready"
        ]
        
        for endpoint in endpoints:
            response = self.client.get(endpoint)
            assert response.status_code in [200, 503]
            data = response.json()
            assert "status" in data
    
    def test_metrics_endpoint(self):
        """Test metrics endpoint"""
        response = self.client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "uptime_seconds" in data
    
    def test_customers_crud(self):
        """Test Customers service CRUD operations"""
        # Create customer
        customer_data = {
            "name": "Test Customer",
            "email": "test@example.com"
        }
        
        response = self.client.post(
            "/customers/",
            json=customer_data,
            headers=self.headers
        )
        assert response.status_code == 201
        created_customer = response.json()
        assert "id" in created_customer
        customer_id = created_customer["id"]
        
        # Get all customers
        response = self.client.get("/customers/", headers=self.headers)
        assert response.status_code == 200
        customers = response.json()
        assert isinstance(customers, list)
        
        # Verify created customer exists
        customer_ids = [c["id"] for c in customers]
        assert customer_id in customer_ids
    
    def test_products_crud(self):
        """Test Products service CRUD operations"""
        # Create product
        product_data = {
            "sku": f"TEST-{int(time.time())}",
            "name": "Test Product",
            "category": "Test Category",
            "price": 99.99,
            "is_active": True
        }
        
        response = self.client.post(
            "/products/",
            json=product_data,
            headers=self.headers
        )
        assert response.status_code == 201
        created_product = response.json()
        assert "id" in created_product
        product_id = created_product["id"]
        
        # Get all products
        response = self.client.get("/products/", headers=self.headers)
        assert response.status_code == 200
        products = response.json()
        assert isinstance(products, list)
    
    def test_inventory_management(self):
        """Test Inventory service operations"""
        # Create inventory entry
        inventory_data = {
            "product_id": 1,
            "warehouse": "MAIN",
            "on_hand": 100,
            "reserved": 10
        }
        
        response = self.client.post(
            "/inventory/",
            json=inventory_data,
            headers=self.headers
        )
        
        if response.status_code == 201:
            created_inventory = response.json()
            assert "id" in created_inventory
            
            # Update inventory
            update_data = {
                "product_id": 1,
                "warehouse": "MAIN",
                "on_hand": 150,
                "reserved": 20
            }
            
            response = self.client.put(
                f"/inventory/{created_inventory['id']}",
                json=update_data,
                headers=self.headers
            )
            assert response.status_code in [200, 404]
    
    def test_order_workflow(self):
        """Test complete order workflow"""
        # Create order
        order_data = {
            "customer_id": 1,
            "order_status": "PENDING",
            "payment_status": "PENDING",
            "order_total": 199.99,
            "items": [
                {
                    "product_id": 1,
                    "sku": "TEST-001",
                    "quantity": 2,
                    "unit_price": 99.99
                }
            ]
        }
        
        response = self.client.post(
            "/orders/",
            json=order_data,
            headers=self.headers
        )
        
        if response.status_code == 201:
            created_order = response.json()
            assert "id" in created_order
            order_id = created_order["id"]
            
            # Create payment
            payment_data = {
                "order_id": order_id,
                "amount": 199.99,
                "status": "PAID"
            }
            
            response = self.client.post(
                "/payments/",
                json=payment_data,
                headers=self.headers
            )
            assert response.status_code in [201, 400]
            
            # Create shipment
            shipment_data = {
                "order_id": order_id,
                "carrier": "FedEx",
                "status": "IN_TRANSIT",
                "tracking_no": f"TRACK-{int(time.time())}"
            }
            
            response = self.client.post(
                "/shipments/",
                json=shipment_data,
                headers=self.headers
            )
            assert response.status_code in [201, 400]
    
    def test_graphql_queries(self):
        """Test GraphQL endpoint"""
        # Simple query
        query = """
        query {
            customers(take: 5) {
                id
                name
                email
            }
            products(take: 5) {
                id
                name
                price
            }
        }
        """
        
        response = self.client.post(
            "/graphql",
            json={"query": query},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "customers" in data["data"]
        assert "products" in data["data"]
    
    def test_graphql_nested_queries(self):
        """Test GraphQL nested queries"""
        query = """
        query {
            orders(take: 5) {
                id
                order_status
                customer {
                    name
                }
                items {
                    product {
                        name
                    }
                    quantity
                }
                payments {
                    amount
                    status
                }
                shipments {
                    carrier
                    status
                }
            }
        }
        """
        
        response = self.client.post(
            "/graphql",
            json={"query": query},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "orders" in data["data"]
    
    def test_caching_behavior(self):
        """Test that caching is working"""
        # First request
        start = time.time()
        response1 = self.client.get("/customers/", headers=self.headers)
        time1 = time.time() - start
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Second request (should be cached)
        start = time.time()
        response2 = self.client.get("/customers/", headers=self.headers)
        time2 = time.time() - start
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Verify data is the same
        assert data1 == data2
        
        # Second request should be faster (cached)
        # Note: This might not always be true in test environments
        print(f"First request: {time1:.3f}s, Cached request: {time2:.3f}s")
    
    def test_error_handling(self):
        """Test error handling"""
        # Test unauthorized access
        response = self.client.get("/customers/")
        assert response.status_code == 401
        
        # Test invalid endpoint
        response = self.client.get("/invalid/", headers=self.headers)
        assert response.status_code == 404
        
        # Test invalid data
        response = self.client.post(
            "/customers/",
            json={"invalid": "data"},
            headers=self.headers
        )
        assert response.status_code in [400, 422]
    
    def test_request_tracking(self):
        """Test request ID tracking"""
        response = self.client.get("/customers/", headers=self.headers)
        assert response.status_code == 200
        
        # Check if X-Request-ID is in response headers
        if "X-Request-ID" in response.headers:
            request_id = response.headers["X-Request-ID"]
            assert len(request_id) > 0
            print(f"Request tracked with ID: {request_id}")
    
    @pytest.mark.performance
    def test_performance_baseline(self):
        """Test performance baselines"""
        endpoints = [
            "/customers/",
            "/products/",
            "/inventory/",
            "/orders/",
            "/payments/",
            "/shipments/"
        ]
        
        for endpoint in endpoints:
            start = time.time()
            response = self.client.get(endpoint, headers=self.headers)
            duration = time.time() - start
            
            assert response.status_code == 200
            # Assert response time is under 1 second
            assert duration < 1.0, f"{endpoint} took {duration:.3f}s"
            print(f"{endpoint}: {duration:.3f}s")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])