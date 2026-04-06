-- Seed data: customers and products for the simulator to use

INSERT INTO customers (email, name) VALUES
    ('kim.minjun@example.com', 'Kim Minjun'),
    ('lee.soyeon@example.com', 'Lee Soyeon'),
    ('park.jihoon@example.com', 'Park Jihoon'),
    ('choi.yuna@example.com', 'Choi Yuna'),
    ('jung.taewoo@example.com', 'Jung Taewoo'),
    ('han.eunji@example.com', 'Han Eunji'),
    ('oh.seungwoo@example.com', 'Oh Seungwoo'),
    ('yoon.haeun@example.com', 'Yoon Haeun'),
    ('shin.dongho@example.com', 'Shin Dongho'),
    ('kwon.minji@example.com', 'Kwon Minji');

INSERT INTO products (name, category, base_price) VALUES
    ('Samsung Galaxy S25', 'electronics', 1190000),
    ('Apple AirPods Pro', 'electronics', 359000),
    ('LG 65" OLED TV', 'electronics', 2490000),
    ('Nike Air Max 90', 'clothing', 169000),
    ('Adidas Ultraboost', 'clothing', 219000),
    ('Uniqlo Down Jacket', 'clothing', 99000),
    ('Instant Ramen 5-pack', 'food', 4500),
    ('Organic Milk 1L', 'food', 3200),
    ('Premium Coffee Beans 1kg', 'food', 28000),
    ('Dyson V15 Vacuum', 'home', 899000),
    ('IKEA Desk Lamp', 'home', 29000),
    ('Coupang Rocket Delivery Box', 'home', 15000),
    ('Nintendo Switch OLED', 'electronics', 415000),
    ('Sony WH-1000XM5', 'electronics', 429000),
    ('New Balance 990v6', 'clothing', 259000);

-- Set initial inventory (all products in stock)
INSERT INTO inventory (product_id, quantity, reserved)
SELECT id, 100 + (random() * 200)::int, 0
FROM products;
