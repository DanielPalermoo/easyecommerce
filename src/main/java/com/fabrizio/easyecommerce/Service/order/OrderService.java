package com.fabrizio.easyecommerce.Service.order;

import com.fabrizio.easyecommerce.dto.order.OrderResponseDTO;

import java.util.List;

public interface OrderService {

    OrderResponseDTO performCheckout(Long userId);

    OrderResponseDTO performCheckoutByEmail(String email);

    List<OrderResponseDTO> getMyOrders(String email);

    OrderResponseDTO getOrderById(Long orderId);

    List<OrderResponseDTO> getAllOrders();

    void updateOrderStatus(Long orderId, String status);
}
