# G-Study – English 10 Learning Platform

G-Study là ứng dụng học tiếng Anh 10 dùng Python (thư viện chuẩn) và SQLite. Phiên bản này giữ lại dữ liệu học hiện có, bổ sung giao diện điện thoại 4 tab và cổng quản trị tập trung.

## 1. Chạy trên máy tính

Yêu cầu Python 3.10 trở lên. Không cần cài thư viện ngoài.

```bash
cd english10_duolingo
python3 server.py
```

Mở ứng dụng tại `http://localhost:8090`. Cổng quản trị nằm tại `http://localhost:8090/admin`.

## 2. Tài khoản quản trị

- Email quản trị: `admin@lingo10.vn`
- Mật khẩu ban đầu được bàn giao riêng cho chủ dự án; không đưa mật khẩu quản trị vào mã giao diện hoặc repository công khai.
- Đường dẫn quản trị: `/admin` (cùng tên miền với ứng dụng)

Nên đăng nhập bằng tài khoản quản trị và đổi mật khẩu ngay trong **Cá nhân → Đổi mật khẩu** sau khi triển khai. Mật khẩu được lưu dạng PBKDF2 hash trong SQLite, không được nhúng vào giao diện học sinh.

## 3. Các phần đã có

### Ứng dụng học sinh
- Thanh điều hướng mobile cố định phía dưới: **Trang chủ, Lộ trình, Thống kê, Cá nhân**.
- Trang chủ: tiếp tục lộ trình, tổng quan kết quả, hoạt động học hôm nay, tiến độ gần đây và mục tiêu tuần.
- Lộ trình: hiển thị các Unit và kỹ năng lấy trực tiếp từ dữ liệu trên máy chủ; lưu tiến độ riêng cho từng kỹ năng và tự chọn kỹ năng chưa hoàn thành để học tiếp.
- Thống kê: điểm trung bình, tổng lượt học, thời gian học, kết quả gần đây và tiến độ theo Unit.
- Cá nhân: đổi mật khẩu, liên hệ admin `0888074418`, gửi đánh giá và đường dẫn vào web admin.

### Web admin `/admin`
- Tổng quan số lượng tài khoản, hoạt động, điểm và bài học.
- Quản lý học sinh: xem thống kê, khóa/mở khóa và đặt mật khẩu tạm.
- Quản lý nội dung: thêm/sửa/xóa bài học, kỹ năng và câu hỏi.
- Theo dõi lịch sử lượt học.
- Đọc đánh giá, góp ý từ người học.
- Cài đặt tên ứng dụng, số điện thoại hỗ trợ, mục tiêu học tuần và trạng thái mở đăng ký.

## 4. Triển khai có lưu dữ liệu

Ứng dụng hiện sử dụng Python HTTP server và SQLite. Nên triển khai trên dịch vụ hỗ trợ ứng dụng Python chạy liên tục và ổ đĩa lưu trữ bền vững (ví dụ Render Web Service có Persistent Disk).

Trong repository đã có `render.yaml` cấu hình mẫu. Khi tạo dịch vụ:

1. Đưa thư mục dự án lên GitHub.
2. Tạo Web Service từ repository và dùng Blueprint `render.yaml`.
3. Đảm bảo Persistent Disk được gắn tại `/var/data`.
4. Kiểm tra biến `DB_PATH=/var/data/english10.db` và mở URL dịch vụ sau khi deploy.
5. Đăng nhập bằng tài khoản quản trị ở mục 2; vào `/admin` để quản lý app.

`server.py` tự sao chép cơ sở dữ liệu `english10.db` đi kèm vào ổ đĩa bền vững ở lần khởi chạy đầu nếu ổ đĩa chưa có DB.

### Biến môi trường

| Tên | Ý nghĩa |
|---|---|
| `PORT` | Cổng HTTP, mặc định `8090` (nền tảng hosting có thể tự cấp) |
| `DB_PATH` | Đường dẫn SQLite; dùng `/var/data/english10.db` khi gắn disk |
| `ADMIN_EMAIL` | Email admin, mặc định `admin@lingo10.vn` |
| `ADMIN_PASSWORD` | Mật khẩu khởi tạo admin khi tạo DB mới và chưa có admin |
| `RESET_ADMIN_PASSWORD` | Đặt `1` cùng `ADMIN_PASSWORD` để xoay mật khẩu admin khi khởi động; bỏ biến này sau khi đổi xong |

## 5. Lưu ý triển khai

- Không nên triển khai bản Python + SQLite này như một static site trên Vercel. Vercel không giữ tiến trình HTTP server lâu dài và hệ thống tệp serverless không phù hợp để lưu file SQLite thay đổi liên tục. Muốn tiếp tục dùng Vercel cần chuyển API sang Functions và chuyển cơ sở dữ liệu sang dịch vụ bền vững như PostgreSQL.
- `english10.db` chứa dữ liệu tài khoản và tiến độ học tập hiện tại. Giữ file này riêng tư, bật HTTPS và sao lưu ổ đĩa dữ liệu định kỳ.
- Tính năng quên mật khẩu tự động qua email chưa được kết nối SMTP; người học có thể liên hệ admin để được hỗ trợ.
- Nút đăng nhập Google không được hiển thị như một luồng đăng nhập giả. Muốn bật Google OAuth cần cấu hình Client ID/Secret và callback thật.
