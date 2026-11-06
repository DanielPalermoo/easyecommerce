package com.fabrizio.easyecommerce.Service.product;

import com.fabrizio.easyecommerce.dto.product.ProductRequestDTO;
import com.fabrizio.easyecommerce.dto.product.ProductResponseDTO;

import java.util.List;

public interface ProductService {
    List<ProductResponseDTO> getAllProducts();
    ProductResponseDTO getProductById(Long id);
    void creteProduct(ProductRequestDTO request);
    void updateProduct(Long id, ProductRequestDTO request);
    void deleteProduct(Long id);
}
