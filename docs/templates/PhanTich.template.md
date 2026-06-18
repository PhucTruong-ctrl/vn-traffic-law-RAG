**APP QUẢN LÝ NHÀ TRỌ**

1.  **Xác định actor:**

-   Những người muốn thuê nhà trọ vào website để xem thông tin. Những
    người này gọi là **Khách hàng tiềm năng(Guest).**

-   Những người đã thuê phòng trọ, thanh toán,... gọi là **Khách
    hàng(Custom).**

-   Người đăng bài cho thuê phòng trọ, quản lý phòng trọ, thu tiền, theo
    dõi các giao dịch, gọi là **Chủ trọ(Manager).**

-   Người có quyền cao nhất có thể quản lý tài khoản người dùng bao gồm
    khách hàng và chủ trọ, quản lý dãy trọ đó, quản lý các giao dịch
    được thực hiện được gọi là **Người quản trị hệ thống(Admin).**

2.  **Xác định các Use-Case:**

    1.  **Khách hành tiềm năng(Guest):**

-   **Xem danh sách phòng trọ:** Khi người dùng truy cập vào ứng dụng
    với vai trò là khách hàng tiềm năng, họ sẽ được cung cấp một danh
    sách tổng hợp các phòng trọ đang cho thuê. Danh sách này bao gồm các
    dãy trọ và phòng trọ với thông tin cơ bản như: tên phòng, giá thuê,
    khu vực, diện tích, trạng thái (trống hoặc đã thuê),\... Mục đích là
    giúp người dùng dễ dàng so sánh, chọn lọc và định hình lựa chọn phù
    hợp với nhu cầu của mình.

-   **Xem chi tiết phòng trọ:** Đối với những phòng trọ mà khách hàng
    tiềm năng cảm thấy hứng thú, họ có thể truy cập vào phần chi tiết để
    xem kỹ hơn các thông tin cụ thể. Phần này sẽ hiển thị giá thuê, chi
    phí điện -- nước, diện tích, thời gian cho thuê, mô tả tiện nghi,
    cùng với một số hình ảnh thực tế của căn phòng. Điều này giúp người
    dùng đánh giá tổng thể phòng trọ trước khi đưa ra quyết định có nên
    thuê hay không.

-   **Tìm kiếm phòng trọ theo tiêu chí (giá, khu vực, tiện ích,...):**
    Khách hàng tiềm năng không cần phải duyệt qua toàn bộ danh sách
    phòng trọ một cách thủ công. Thay vào đó, họ có thể sử dụng chức
    năng tìm kiếm nâng cao bằng cách nhập các tiêu chí cụ thể như mức
    giá mong muốn, khu vực sinh sống (quận, phường), hoặc các tiện ích
    kèm theo như máy lạnh, chỗ để xe, wifi miễn phí,\... Tính năng này
    giúp quá trình tìm kiếm trở nên nhanh chóng, hiệu quả và sát với nhu
    cầu thực tế hơn.

-   **Đăng ký tài khoản (để trở thành khách hàng**): Sau khi đã lựa chọn
    được phòng trọ phù hợp và muốn thực hiện việc thuê, khách hàng tiềm
    năng bắt buộc phải tiến hành đăng ký tài khoản trên hệ thống. Việc
    đăng ký yêu cầu cung cấp một số thông tin cá nhân cơ bản như họ tên,
    số điện thoại, email, và mật khẩu. Sau khi tài khoản được tạo thành
    công, người dùng sẽ được chuyển sang vai trò \"Khách hàng
    (Customer)\" và có quyền sử dụng các chức năng nâng cao như ký hợp
    đồng thuê, thanh toán tiền phòng, gửi yêu cầu bảo trì,\...

> ![A black and white screen with white text AI-generated content may be
> incorrect.](media/image1.png){width="6.740972222222222in"
> height="4.486111111111111in"}**Bản vẽ Use-Case cho Actor "Khách hàng
> tiềm năng"**

1.  **Khách hàng(Custom):**

-   **Đăng nhập:** Sau khi hoàn tất việc đăng ký tài khoản, khách hàng
    có thể sử dụng thông tin đăng nhập (tên đăng nhập và mật khẩu) để
    truy cập vào hệ thống. Việc đăng nhập là điều kiện bắt buộc để khách
    hàng có thể sử dụng các chức năng nâng cao như thanh toán tiền
    phòng, xem lịch sử thuê trọ, gửi yêu cầu hỗ trợ,\... Khi đăng nhập
    thành công, hệ thống sẽ xác định vai trò là "Customer" để hiển thị
    các chức năng phù hợp

-   **Xem và sửa profile cá nhân:** Khách hàng sau khi đăng nhập vào hệ
    thống có thể truy cập phần quản lý tài khoản để cập nhật các thông
    tin cá nhân của mình. Bao gồm: họ và tên, số điện thoại, địa chỉ
    email và các thông tin liên hệ khác. Việc cập nhật thông tin kịp
    thời giúp chủ trọ liên lạc dễ dàng với khách hàng khi cần thiết .

-   **Xem danh sách phòng thuê:** Khách hàng có thể xem tất cả các phòng
    trọ mà mình đang thuê thông qua một giao diện danh sách rõ ràng.
    Thông tin mỗi phòng bao gồm: địa chỉ, diện tích, giá thuê, thời hạn
    hợp đồng, trạng thái thanh toán,\... Tính năng này giúp khách hàng
    quản lý hiệu quả việc thuê trọ của mình, đặc biệt trong trường hợp
    khách thuê nhiều phòng cùng lúc.

-   **Thanh toán tiền phòng:** Đến mỗi kỳ thanh toán (ví dụ: mỗi tháng),
    khách hàng sẽ nhận được thông báo và có thể tiến hành thanh toán
    tiền phòng thông qua hệ thống. Các hình thức thanh toán hỗ trợ bao
    gồm: tiền mặt (trực tiếp cho chủ trọ), chuyển khoản ngân hàng, hoặc
    thanh toán qua ví điện tử. Hệ thống sẽ lưu lại thông tin giao dịch
    và xác nhận khi thanh toán hoàn tất.

-   **Xem lịch sử thanh toán:** Sau khi khách hàng thực hiện thanh toán
    thành công, họ có thể truy cập vào mục "Lịch sử thanh toán" để kiểm
    tra toàn bộ các giao dịch đã thực hiện. Mỗi mục sẽ bao gồm: thời
    gian thanh toán, số tiền, hình thức thanh toán, và trạng thái (đã
    xác nhận/chờ xác nhận). Điều này giúp khách hàng theo dõi chi tiêu
    và khiếu nại nếu có sai sót xảy ra.

-   **Gửi yêu cầu hỗ trợ / bảo trì:** Trong quá trình thuê phòng, nếu
    khách hàng gặp sự cố như hư hỏng thiết bị (điện, nước, quạt, máy
    lạnh,\...), cần sửa chữa cơ sở vật chất, hoặc có những thắc mắc liên
    quan đến phòng trọ, họ có thể gửi yêu cầu hỗ trợ đến chủ trọ thông
    qua hệ thống. Yêu cầu này sẽ được ghi nhận lại kèm thời gian và nội
    dung, giúp chủ trọ xử lý nhanh chóng và có trách nhiệm hơn.

![A black and white screen with white circles AI-generated content may
be incorrect.](media/image2.png){width="6.740972222222222in"
height="4.970138888888889in"}

> **Bản vẽ Use-Case cho Actor "Khách hàng"**

1.  **Chủ trọ(Manager):**

-   **Đăng nhập:** Để bắt đầu sử dụng các chức năng quản lý trên hệ
    thống, chủ trọ cần đăng nhập vào tài khoản đã đăng ký từ trước.
    Thông tin đăng nhập bao gồm số điện thoại/email và mật khẩu. Ngoài
    ra, trong hồ sơ cá nhân, chủ trọ cần cung cấp đầy đủ thông tin như
    họ tên, số CCCD/CMND, địa chỉ dãy trọ, số điện thoại,\... nhằm đảm
    bảo xác thực quyền sở hữu và tăng tính minh bạch trong quá trình cho
    thuê.

-   **Quản lý danh sách phòng trọ:** Chủ trọ có thể toàn quyền quản lý
    các phòng trọ trong hệ thống. Bao gồm các thao tác:

    -   **Thêm phòng trọ:** Tạo mới phòng trọ và gán vào dãy trọ tương
        ứng. Nhập đầy đủ thông tin như tên phòng, giá thuê, tiện ích,
        diện tích, hình ảnh,\...

    -   **Chỉnh sửa thông tin phòng:** Thay đổi thông tin khi có cập
        nhật thực tế (giá phòng thay đổi, nâng cấp phòng, điều chỉnh
        tiện ích\...).

    -   **Xóa phòng trọ:** Xóa phòng khỏi danh sách khi không còn nhu
        cầu cho thuê hoặc phòng đang trong quá trình sửa chữa.

-   **Duyệt yêu cầu thuê phòng:** Khi có khách hàng gửi yêu cầu thuê
    phòng, chủ trọ có thể xem xét các thông tin cá nhân, lịch sử thuê
    (nếu có) và đưa ra quyết định phê duyệt hoặc từ chối. Hợp đồng thuê
    chỉ chính thức có hiệu lực sau khi được chủ trọ xác nhận. Điều này
    giúp đảm bảo tính pháp lý và kiểm soát được người thuê.

-   **Quản lý thanh toán:** Chức năng này cho phép chủ trọ:

    -   **Xác nhận thanh toán:** Kiểm tra và xác nhận khi khách hàng đã
        thanh toán xong (qua chuyển khoản, tiền mặt\...).

    -   **Ghi nhận công nợ:** Lưu lại các khoản khách hàng còn nợ và
        theo dõi quá trình thanh toán.

    -   **Sửa thông tin thanh toán:** Điều chỉnh nếu nhập sai (số tiền,
        thời gian\...).

    -   **Xoá giao dịch:** Xoá khi giao dịch bị trùng, lỗi hoặc yêu cầu
        huỷ từ hai bên.

-   **Xem lịch sử giao dịch:** Toàn bộ các giao dịch phát sinh giữa chủ
    trọ và khách hàng sẽ được lưu lại trong hệ thống. Mỗi mục lịch sử sẽ
    ghi rõ thời gian thực hiện, hình thức thanh toán, số tiền, người
    thực hiện, trạng thái giao dịch,\... giúp chủ trọ có cái nhìn tổng
    quan và minh bạch tài chính.

-   **Quản lý thông báo và phản hồi:**

    -   Vào đầu mỗi kỳ thanh toán (ví dụ: đầu tháng), chủ trọ có thể gửi
        thông báo đến từng khách hàng đang thuê phòng. Nội dung thông
        báo bao gồm: số tiền cần thanh toán, hạn thanh toán, các khoản
        phụ thu (nếu có), và hướng dẫn thanh toán. Việc thông báo được
        gửi qua hệ thống nhằm nhắc nhở kịp thời, giảm tình trạng chậm
        trễ hoặc nợ xấu.

        -   **Thêm thông báo:** Tạo và gửi thông báo mới theo từng kỳ
            thanh toán.

        -   **Xoá thông báo:** Xoá khi không còn giá trị hoặc bị gửi
            nhầm.

<!-- -->

-   Trong quá trình thuê phòng, khách hàng có thể gửi các yêu cầu như
    sửa chữa thiết bị hỏng hóc, vệ sinh phòng, hoặc phản hồi về chất
    lượng dịch vụ. Chủ trọ có thể xem, phản hồi và đưa ra phương án xử
    lý phù hợp thông qua hệ thống. Việc tương tác này giúp nâng cao trải
    nghiệm của khách thuê và tăng độ uy tín cho chủ trọ.

    -   **Xem và phản hồi:** Xử lý các phản hồi của khách thuê.

    -   **Cập nhật trạng thái:** Đã xử lý, đang xử lý, từ chối yêu cầu.

    -   **Xoá phản hồi:** Nếu yêu cầu đã cũ, bị spam hoặc không còn cần
        thiết.

![A black and white screen with many white circles AI-generated content
may be incorrect.](media/image3.png){width="6.740972222222222in"
height="3.842361111111111in"}

**Bản vẽ Use-Case của chủ trọ**

1.  **Người quản trị hệ thống(Admin):** Kế thừa tất cả các chức năng của
    Actor chủ trọ

-   **Đăng nhập hệ thống quản trị:** Để truy cập vào các chức năng quản
    trị cấp cao, Admin bắt buộc phải đăng nhập vào hệ thống bằng tài
    khoản quản trị viên. Thông tin đăng nhập bao gồm tên đăng nhập và
    mật khẩu. Chỉ những tài khoản đã được gán quyền quản trị mới có thể
    truy cập vào giao diện và chức năng quản trị của hệ thống.

-   **Quản lý tài khoản người dùng:** Admin có quyền thực hiện các thao
    tác liên quan đến tài khoản người dùng, bao gồm:

    -   **Thêm:** Tạo mới tài khoản cho người dùng (khách hàng hoặc chủ
        trọ) khi có nhu cầu.

    -   **Sửa:** Chỉnh sửa thông tin người dùng như họ tên, số điện
        thoại, email, trạng thái tài khoản,\... trong trường hợp phát
        hiện sai sót hoặc người dùng yêu cầu cập nhật.

    -   **Xóa:** Xóa hoặc khóa tài khoản người dùng nếu phát hiện vi
        phạm chính sách sử dụng, gian lận hoặc có hành vi không phù hợp.

-   **Quản lý dãy trọ:** Admin có thể theo dõi toàn bộ dãy trọ đã được
    đăng lên hệ thống, bao gồm:

    -   **Thêm dãy trọ:** Khi chủ trọ đăng ký mới dãy trọ hoặc Admin
        thêm tay.

    -   **Sửa dãy trọ:** Cập nhật địa chỉ, tiện ích, chủ sở hữu\...

    -   **Xoá dãy trọ:** Khi không còn hoạt động hoặc vi phạm quy định.

-   **Quản lý các giao dịch:** Admin có quyền giám sát tất cả các giao
    dịch trong hệ thống như: thanh toán tiền phòng, hợp đồng thuê
    phòng,\... Admin có thể:

    -   **Xem và kiểm tra giao dịch:** Toàn bộ lịch sử thanh toán, hợp
        đồng.

    -   **Sửa thông tin giao dịch:** Nếu phát hiện sai lệch hoặc có báo
        lỗi.

    -   **Xoá giao dịch:** Khi xác định sai hoặc bị lặp giao dịch.

-   **Phân quyền người dùng:** Tính năng này cho phép Admin gán vai trò
    cho người dùng phù hợp:

    -   Gán quyền **Khách hàng** cho người thuê.

    -   Gán quyền **Chủ trọ** cho người sở hữu dãy trọ.

    -   Cập nhật hoặc thay đổi quyền nếu vai trò người dùng thay đổi.

-   **Thống kê hệ thống:**Admin có thể xem các thống kê tổng hợp toàn hệ
    thống để đánh giá hiệu suất vận hành, bao gồm:

    -   Tổng doanh thu của hệ thống theo ngày, tháng hoặc năm.

    -   Số lượng người thuê đang hoạt động.

    -   Số lượng chủ trọ đang đăng bài.

    -   Tổng số phòng trọ được đăng tải.

-   **Trả lời phản hồi:** Người dùng trong hệ thống (khách hàng hoặc chủ
    trọ) có thể gửi báo cáo về các vấn đề họ gặp phải như:

    -   **Xem phản hồi:** Từ khách hàng hoặc chủ trọ.

    -   **Sửa xử lý phản hồi:** Cập nhật trạng thái đã giải quyết hay
        chưa.

    -   **Xoá phản hồi:** Khi hoàn tất xử lý hoặc báo cáo sai.

![A black background with white ovals AI-generated content may be
incorrect.](media/image4.png){width="6.740972222222222in"
height="3.8333333333333335in"}

**Bản vẽ sơ đồ Use-Case của Actor "Quản trị hệ thống"**

**\*\*\*Kịch bản các Use-Case:**

1.  **Kịch bản Use-Case Đăng ký tài khoản:**

+--------------------+-------------------------------------------------+
| Tên use case       | Đăng ký tài khoản                               |
+====================+=================================================+
| Tên Actor          | Khách hàng tiềm năng                            |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | 1.  Người dùng chưa có tài khoản                |
|                    |                                                 |
|                    | 2.  Truy cập được internet và đến được trang    |
|                    |     "Đăng ký"                                   |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Form "Đăng ký" hiển thị đầy đủ các trường: Họ & |
|                    | tên, SĐT, Giới tính, Quê quán                   |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Tài khoản mới được tạo, hiển thị "Đăng ký thành |
|                    | công" và chuyển sang trang chủ                  |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Khách hàng tiềm năng bấm vào "Đăng ký tài       |
|                    | khoản"                                          |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Khách hàng     | 1.  Tải xuống và hiển thị form Đăng ký lên:     |
| tiềm năng đưa con  |                                                 |
| trỏ (hoặc bấm) vào | -   Họ và tên                                   |
| "Đăng ký tài       |                                                 |
| khoản" trên menu.  | -   Số điện thoại                               |
|                    |                                                 |
|                    | -   Giới tính(dropdown: Nam/Nữ/Khác)            |
|                    |                                                 |
|                    | -   Quê quán                                    |
|                    |                                                 |
|                    | -   Email                                       |
|                    |                                                 |
|                    | -   Ngày sinh                                   |
|                    |                                                 |
|                    | -   Mật khẩu                                    |
+--------------------+-------------------------------------------------+
| 2\. Khách hàng     | 2.1 Hệ thống kiểm tra thông tin hợp lệ:         |
| nhập lần lượt: Họ  |                                                 |
| & tên, SĐT, chọn   | a\) Không để trống bất kỳ trường nào.           |
| Giới tính, nhập    |                                                 |
| Quê quán, rồi nhấn | b\) "Họ và tên" \<= 50 ký tự                    |
| nút "Đăng ký"      |                                                 |
|                    | c\) Số điện thoại đúng(10/11 chữ số, bắt đầu từ |
|                    | 0).                                             |
|                    |                                                 |
|                    | 2.2 Nếu có lỗi: điền thông tin sai trường thì   |
|                    | hệ thống sẽ hiển thị thông báo "Vui lòng kiểm   |
|                    | tra lại dữ liệu" và dừng ở bước này.            |
+--------------------+-------------------------------------------------+
| 3.  Bước 2 hợp     | 1.  Kiểm tra CSDL xem SĐT đã tồn tại chưa:      |
|     lệ - hệ thống  |                                                 |
|     tiếp tục tự    | -   Nếu có: báo lỗi "Số điện thoại đã tồn tại", |
|     động           |     quay lại bước 2.                            |
|                    |                                                 |
|                    | -   Nếu chưa: tiếp tục.                         |
+--------------------+-------------------------------------------------+
| 4.  Nếu SĐT chưa   | 1.  Sinh id_user.                               |
|     tồn tại        |                                                 |
|                    | 2.  Ghi bản ghi vào bảng Users.                 |
|                    |                                                 |
|                    | 3.  Hiện "Đăng ký thành công"\\                 |
|                    |                                                 |
|                    | 4.  Chuyển hướng về trang chủ                   |
+--------------------+-------------------------------------------------+

2.  **Kịch bản Use-Case Xem danh sách phòng trọ:**

+--------------------+-------------------------------------------------+
| Tên use case       | Xem danh sách phòng trọ                         |
+====================+=================================================+
| Tên Actor          | Khách hàng tiềm năng                            |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Khách hàng vào được trang chủ (không bắt buộc   |
|                    | đăng nhập)                                      |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Giao diện "Danh sách phòng trọ" hiện ra (có thể |
|                    | rỗng)                                           |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Hiển thị đầy đủ thông tin danh sách phòng trọ   |
|                    | đang có trên hệ thống                           |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Khách hàng click vào menu "Danh sách phòng trọ" |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Khách hàng bấm | 1.1 Hệ thống tiến hành truy vấn CSDL lấy toàn   |
| chọn "Danh sách    | bộ các phòng.                                   |
| phòng trọ".        |                                                 |
|                    | 1.2 Hiển thị giao diện dạng lưới hoặc danh      |
|                    | sách, mỗi mục bao gồm: ảnh, tiêu đề, khu vực,   |
|                    | giá, mô tả ngắn.                                |
+--------------------+-------------------------------------------------+
| **Luồng thay thế** |                                                 |
+--------------------+-------------------------------------------------+
| A1 -- không có     | 1.2.1 nếu kết quả trả về rỗng:                  |
| phòng trọ nào      |                                                 |
| trong CSDL         | \- Hệ thống hiển thị thông báo: "Hiện chưa có   |
|                    | phòng nào. Vui lòng thử lại sau".               |
|                    |                                                 |
|                    | \- Kết thúc Use-Case, vẫn hiển thị khung danh   |
|                    | sách rỗng.                                      |
+--------------------+-------------------------------------------------+

3.  **Kịch bản của Use-Case Xem chi tiết phòng trọ:**

  -----------------------------------------------------------------------
  Tên use case          Xem chi tiết phòng trọ
  --------------------- -------------------------------------------------
  Tên Actor             Khách hàng tiềm năng

  Mức                   1

  Tiền điều kiện        Đã hiển thị danh sách hoặc kết quả tìm kiếm phòng
                        trọ

  Đảm bảo tối thiểu     Giao diện chi tiết phòng trọ được tải

  Đảm bảo thành công    Hiển thị đầy đủ thông tin chi tiết, hình ảnh,
                        giá, tiện ích, liên hệ chủ trọ

  Kích hoạt             Khách hàng click vào một phòng bất kỳ trong danh
                        sách

  **Hành động tác       **Phản ứng hệ thống**
  nhân**                

  1\. Khách hàng click  1.1. Ghi nhận ID phòng, thời gian truy cập
  vào ô/tiêu đề phòng   
  trọ bất kỳ            

  2\.                   2.1. Truy vấn CSDL chi tiết phòng trọ theo
                        room_id:\
                          - Tiêu đề, mô tả dài\
                          - Bộ ảnh (ảnh chính + album)\
                          - Giá, diện tích, địa chỉ\
                          - Tiện ích (điện, nước, internet, máy lạnh...)\
                          - Thông tin liên hệ chủ trọ (tên, SĐT)\
                          - Ngày đăng, tình trạng phòng

  3\.                   3.1. Hiển thị lên giao diện:\
                          - Hiện thanh album ảnh\
                          - Hiện các "Mô tả", "Tiện ích", "Liên hệ"\
                          - Nút "Đặt thuê" và "Liên hệ ngay"

  4\. Khách hàng        4.1. Nếu click ảnh, phóng to ảnh.\
  cuộn/xem qua các mục  4.2. Nếu bấm "Liên hệ", thì sẽ liên hệ trực tiếp
                        với chủ trọ 4.3. Nếu bấm "Đặt thuê", chuyển sang
                        Use Case "Thuê phòng trọ".
  -----------------------------------------------------------------------

4.  **Kịch bản Use-Case Tìm kiếm phòng trọ:**

  -----------------------------------------------------------------------
  Tên use case          Tìm kiếm phòng trọ
  --------------------- -------------------------------------------------
  Tên Actor             Khách hàng tiềm năng

  Mức                   1

  Tiền điều kiện        Giao diện "Danh sách phòng trọ" đã hiển thị hoặc
                        khách hàng đã vào được trang tìm kiếm

  Đảm bảo tối thiểu     Hiển thị form tìm kiếm với các trường: từ khóa,
                        lọc theo giá, khu vực, tiện ích

  Đảm bảo thành công    Hiển thị danh sách phòng trọ thỏa mãn tiêu chí
                        tìm kiếm

  Kích hoạt             Khách hàng click vào nút "Tìm kiếm"

  **Hành động tác       **Phản ứng hệ thống**
  nhân**                

  1\. Khách hàng nhập   1.1. Kiểm tra tính hợp lệ:\
  tiêu chí tìm kiếm:\     - Giá min ≤ Giá max.\
  -- Giá\                 - Định dạng số hợp lệ.\
  -- Khu vực\           1.2. Nếu hợp lệ, chuyển sang bước 2; nếu không,
  -- Tiện ích           hiện lỗi "Vui lòng kiểm tra khoảng giá."

  2\. Khách hàng nhấn   2.1. Hệ thống truy vấn CSDL với điều kiện:\
  nút "Tìm kiếm"          - Giá\
                          - Khu vực\
                          - Tiện ích\
                        2.2. Trả về danh sách kết quả

  3\.                   3.1. Hiển thị kết quả dưới dạng danh sách/ô lưới,
                        gồm ảnh, tiêu đề, giá, khu vực.\
                        3.2. Nếu có \>20 kết quả, phân trang (hoặc
                        infinite scroll).\
                        3.3. Cho phép khách hàng nhấp vào từng phòng để
                        xem chi tiết.
  -----------------------------------------------------------------------

5.  **Kịch bản Use-Case Đăng nhập:**

+--------------------+-------------------------------------------------+
| Tên use case       | Đăng nhập                                       |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Khách hàng đã có tài khoản trên hệ thống; đang  |
|                    | ở trang "Đăng nhập"                             |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiển thị form với hai trường: SĐT, Mật khẩu và  |
|                    | hai nút "Đăng nhập" / "Quên mật khẩu"           |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Khách hàng được xác thực, chuyển đến trang chủ  |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Khách hàng nhấn nút "Đăng nhập"                 |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Nhập SĐT và    | 1.1. Kiểm tra định dạng SĐT (10--11 số, bắt đầu |
| Mật khẩu → nhấn    | 0) và độ dài mật khẩu (≥ 6 ký tự).\             |
| "Đăng nhập".       | 1.2. Nếu hợp lệ, "Đăng nhập thành công" và      |
|                    | chuyển sang trang chủ.                          |
+--------------------+-------------------------------------------------+
| **Luồng thay thế** |                                                 |
+--------------------+-------------------------------------------------+
| A1 - Sai SĐT hoặc  | Tại bước 1.2, nếu CSDL không trả về bản ghi hợp |
| mật khẩu           | lệ:                                             |
|                    |                                                 |
|                    | -   Hệ thống hiện thông báo "SĐT hoặc mật khẩu  |
|                    |     không đúng."                                |
|                    |                                                 |
|                    | -   Cho phép khách hàng nhập lại (vẫn ở trang   |
|                    |     Đăng nhập).                                 |
+--------------------+-------------------------------------------------+
| A2 -- Quên mật     | 1.  Trên form, khách hàng bấm "Quên mật khẩu".  |
| khẩu               |                                                 |
|                    | 2.  Hệ thống chuyển sang Use Case **Quên mật    |
|                    |     khẩu** (ForgotPassword).                    |
+--------------------+-------------------------------------------------+

6.  **Kịch bản Use-Case Xem và sửa Profile cá nhân:**

+--------------------+-------------------------------------------------+
| Tên use case       | Xem và sửa profile cá nhân                      |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Đã đăng nhập                                    |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiển thị form profile với các trường: Họ Tên,   |
|                    | SĐT, Giới Tính, Quê Quán,...                    |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Thông tin mới được lưu, hiển thị "Cập nhật      |
|                    | thành công"                                     |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Click vào menu "Tài khoản" bấm vào "Profile"    |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Hệ thống tự    | 1.1. Truy vấn CSDL lấy thông tin user; điền vào |
| động load trang    | form.                                           |
| Profile.           |                                                 |
+--------------------+-------------------------------------------------+
| 2\. Khách hàng     | 2.1. Kiểm tra ràng buộc (độ dài, không bỏ       |
| sửa/chỉnh Họ Tên,  | trống).                                         |
| Giới Tính, Quê     |                                                 |
| Quán,...           |                                                 |
+--------------------+-------------------------------------------------+
| 3\. Nhấn "Lưu thay | 3.1. Cập nhật CSDL                              |
| đổi"               |                                                 |
|                    | 3.2. Hiển thị "Cập nhật thành công"             |
+--------------------+-------------------------------------------------+

7.  **Kịch bản Use-Case thay đổi mật khẩu:**

+--------------------+-------------------------------------------------+
| Tên use case       | Thay đổi mật khẩu                               |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 2                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Đã đăng nhập và đang ở trang Profile            |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiện form 3 trường: Mật khẩu cũ, Mật khẩu mới,  |
|                    | Xác nhận mật khẩu mới                           |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Mật khẩu mới được lưu, hiển thị "Đổi mật khẩu   |
|                    | thành công"                                     |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Click "Đổi mật khẩu" trên Profile               |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Nhập mật khẩu  | 1.1. Hệ thống kiểm tra:                         |
| cũ, mật khẩu mới,  |                                                 |
| xác nhận mật khẩu  | -   Mật khẩu cũ đúng hay không.                 |
| mới → nhấn "Xác    |                                                 |
| nhận".             | -   Mật khẩu mới và xác nhận trùng khớp, đủ độ  |
|                    |     dài.                                        |
+--------------------+-------------------------------------------------+
|                    | 2.1. Nếu hợp lệ, cập nhật CSDL; thông báo thành |
|                    | công; ngược lại báo lỗi tương ứng.              |
+--------------------+-------------------------------------------------+

8.  **Kịch bản Use-Case Thay đổi số điện thoại:**

+--------------------+-------------------------------------------------+
| Tên use case       | Thay đổi số điện thoại                          |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 2                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Đã đăng nhập và đang ở trang Profile            |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiện form 2 trường: Số điện thoại mới, OTP      |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | SĐT mới được lưu, hiển thị "Cập nhật thành      |
|                    | công"                                           |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Click "Thay đổi SĐT" trên Profile               |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Nhập SĐT mới   | 1.1. Hệ thống gửi mã OTP                        |
| và nhấn gửi OTP    |                                                 |
+--------------------+-------------------------------------------------+
| 2\. Nhập OTP và    | 2.1. Hệ thống kiểm tra OTP:                     |
| nhấn "Xác nhận".   |                                                 |
|                    | \- Nếu đúng, cập nhật CSDL và hiển thị "Cập     |
|                    | nhật thành công".                               |
|                    |                                                 |
|                    | \- Nếu sai, báo lỗi.                            |
+--------------------+-------------------------------------------------+

**\
**

9.  **Kịch bản Use-Case Xem Danh sách phòng thuê:**

+--------------------+-------------------------------------------------+
| Tên use case       | Xem danh sách phòng thuê                        |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Đã đăng nhập; có ít nhất 1 hợp đồng thuê        |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiển thị bảng (có thể rỗng) gồm: Mã phòng, Tên  |
|                    | phòng, Địa chỉ, Ngày bắt đầu, Ngày kết thúc     |
|                    | ,...                                            |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Hiển thị đầy đủ các phòng đang thuê             |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Click menu "Phòng của tôi"                      |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Click "Phòng   | 1.1. Truy vấn CSDL hợp đồng thuê của người      |
| của tôi".          | dùng.                                           |
|                    |                                                 |
|                    | 1.2. Hiển thị bảng phòng đang thuê.             |
+--------------------+-------------------------------------------------+
| 2\. (Tùy chọn)     | 2.1. Sắp xếp dữ liệu trên giao diện.            |
| Click vào tiêu đề  |                                                 |
| cột để sắp         |                                                 |
| xếp.(Sắp xếp từ A  |                                                 |
| -\> Z)             |                                                 |
+--------------------+-------------------------------------------------+

10. **Kịch bản Use-Case Tìm kiếm phòng đã thuê:**

+--------------------+-------------------------------------------------+
| Tên use case       | Xem danh sách phòng thuê                        |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 2                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Đang ở trang phòng đã thuê                      |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiện ô nhập "Từ khóa"                           |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Lọc & hiện danh sách phù hợp tiêu chí           |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Nhập từ khóa và nhấn "Tìm"                      |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Nhập từ khóa   | 1.1. Truy vấn CSDL                              |
| (Số phòng hoặc Tên |                                                 |
| dãy) → nhấn "Tìm". | 1.2. Hiển thị kết quả tìm kiếm                  |
+--------------------+-------------------------------------------------+
|                    | 2.1. Nếu rỗng, hiện "Không tìm thấy".           |
+--------------------+-------------------------------------------------+

11. **Kịch bản Use-Case Xem lịch sử giao dịch**

+--------------------+-------------------------------------------------+
| Tên use case       | Xem lịch sử giao dịch                           |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Đã đăng nhập                                    |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiển thị form lọc theo ngày/tháng/năm           |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Hiển thị danh sách giao dịch: Ngày, Loại (Thanh |
|                    | toán, Hoàn tiền...), Số tiền                    |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Click menu "Lịch sử giao dịch"                  |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Vào lịch sử    | 1.1. Lấy toàn bộ các giao dịch.                 |
| giao dịch          |                                                 |
|                    | 1.2 Hiển thị bảng: Ngày, Mô tả, Số tiền         |
+--------------------+-------------------------------------------------+
| 2\. Chọn lọc giao  | 2.1. Hệ thống sẽ lọc theo trường ngày bắt đầu   |
| dịch theo          | và ngày kết thúc                                |
| ngày/tháng/năm     |                                                 |
| (nếu muốn)         | 2.2 Hiển thị danh sách giao dịch theo trường đã |
|                    | lọc                                             |
+--------------------+-------------------------------------------------+

**\
**

12. **Kịch bản Use-Case Thanh toán tiền phòng:**

+--------------------+-------------------------------------------------+
| Tên use case       | Thanh toán tiền phòng                           |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Có kỳ thuê đến hạn hoặc quá hạn                 |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiển thị danh sách kỳ chưa thanh toán           |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Hóa đơn phát sinh, trạng thái "Đã đóng"         |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Click menu "Thanh toán tiền phòng"              |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Vào trang      | 1.1. Truy vấn CSDL                              |
| Thanh toán; chọn   |                                                 |
| phòng/ kỳ          | 1.2 Hiển thị bảng kỳ thuê chưa thanh toán       |
+--------------------+-------------------------------------------------+
| 2\. Chọn ô → bấm   | 2.1. Tính tổng; hiển thị xác nhận với tổng tiền |
| "Tiếp tục"         | & phương thức                                   |
+--------------------+-------------------------------------------------+
| 3\. Xác nhận thanh | 3.1 Khi cổng trả về thành công: tạo hóa đơn;    |
| toán               | cập nhật CSDL; gửi thông báo; hiển thị thông    |
|                    | báo                                             |
+--------------------+-------------------------------------------------+

**\
**

13. **Kịch bản Use-Case chọn phương thức thanh toán:**

+--------------------+-------------------------------------------------+
| Tên use case       | Chọn phương thức thanh toán                     |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 2                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Đang ở bước xác nhận thanh toán                 |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Hiện 2 tùy chọn: Chuyển khoản, Tiền mặt         |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Trả về phương thức thanh toán đã chọn để tiếp   |
|                    | tục Use-Case thanh toán                         |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Trên form xác nhận thanh toán                   |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Chọn chuyển    | 1.1. Xác nhận phương thức thanh toán            |
| khoản hoặc tiền    |                                                 |
| mặt                | 2.  Thực hiện thanh toán                        |
+--------------------+-------------------------------------------------+
|                    | Nếu thành công:                                 |
|                    |                                                 |
|                    | -   Hệ thống ghi nhận đã chọn phương thức thanh |
|                    |     toán.                                       |
|                    |                                                 |
|                    | -   Cập nhật trạng thái                         |
|                    |                                                 |
|                    | -   Thông báo "Thanh toán thành công".          |
+--------------------+-------------------------------------------------+

**\
**

14. **Kịch bản Use-Case gửi yêu cầu hỗ trợ**

+--------------------+-------------------------------------------------+
| Tên use case       | Chọn phương thức thanh toán                     |
+====================+=================================================+
| Tên Actor          | Khách hàng                                      |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Đã đăng nhập                                    |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Form: Chọn phòng, Nội dung, Đính kèm hình, Gửi  |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Yêu cầu lưu status "Chờ phản hồi"; hiển thị     |
|                    | "Gửi thành công"                                |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Click menu "Hỗ trợ"                             |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Vào trang Hỗ   | 1.1. truy vấn phòng đang thuê.                  |
| trợ; chọn phòng    |                                                 |
+--------------------+-------------------------------------------------+
| 2\. Nhập nội dung; | 2.1. Kiểm tra; upload file nếu có.              |
| (tùy chọn) đính    |                                                 |
| kèm ảnh            |                                                 |
+--------------------+-------------------------------------------------+
| 3\. Nhấn "Gửi"     | 3.1 Lưu các thông tin phòng, nội dung, file,    |
|                    | trạng thái "Chờ phản hồi");                     |
|                    |                                                 |
|                    | 3.2. Hiển thị "Gửi thành công".                 |
+--------------------+-------------------------------------------------+

**\
**

15. **Kịch bản Use-Case Quản lý trọ**

+--------------------+-------------------------------------------------+
| Tên use case       | Quản Lý Trọ                                     |
+====================+=================================================+
| Tên Actor          | Chủ trọ                                         |
+--------------------+-------------------------------------------------+
| Mức                | 1                                               |
+--------------------+-------------------------------------------------+
| Tiền điều kiện     | Chủ trọ đã đăng nhập vào hệ thống               |
+--------------------+-------------------------------------------------+
| Đảm bảo tối thiểu  | Giao diện "Quản lý trọ" hiển thị danh sách trọ  |
|                    | (có thể rỗng)                                   |
+--------------------+-------------------------------------------------+
| Đảm bảo thành công | Danh sách trọ được tải lên, cho phép            |
|                    | Thêm/Sửa/Xóa trọ                                |
+--------------------+-------------------------------------------------+
| Kích hoạt          | Chủ trọ click vào menu "Quản lý trọ"            |
+--------------------+-------------------------------------------------+
| **Hành động tác    | **Phản ứng hệ thống**                           |
| nhân**             |                                                 |
+--------------------+-------------------------------------------------+
| 1\. Chủ trọ chọn   | 1.1. Truy vấn CSDL lấy toàn bộ các trọ thuộc    |
| "Quản lý trọ"      | quyền quản lý của chủ trọ.                      |
|                    |                                                 |
|                    | 1.2. Hiển thị lên giao diện bảng danh sách trọ  |
|                    | với các cột: Mã trọ, Tên trọ, Địa chỉ, Số       |
|                    | phòng, Trạng thái,..                            |
+--------------------+-------------------------------------------------+
| 2\. Chủ trọ nhìn   | 2.1 Hệ thống chờ nhận thao tác                  |
| bảng và quyết định |                                                 |
| thao tác           |                                                 |
+--------------------+-------------------------------------------------+
| 3a. Nếu Chủ trọ    | 3.1 Nhận thao tác "Thêm mới" của chủ trọ.       |
| bấm "Thêm"         |                                                 |
|                    | 3.2. Tiến hành "Thêm mới" trọ vào CSDL với các  |
|                    | thông tin như Mã trọ, Tên trọ, Địa chỉ, Số      |
|                    | phòng, Trạng thái,..                            |
|                    |                                                 |
|                    | 3.3. Thông báo "Thêm mới" trọ thành công.       |
+--------------------+-------------------------------------------------+
| 3b. Nếu Chủ trọ    | 3.1 Nhận thao tác "Sửa" của chủ trọ.            |
| bấm "Sửa"          |                                                 |
|                    | 3.2. Nhận thông tin của trọ mà chủ trọ muốn     |
|                    | "Sửa" khi chủ trọ bấm vào.                      |
|                    |                                                 |
|                    | 3.3. Tiến hành "Sửa" thông tin của trọ như Mã   |
|                    | trọ, Tên trọ, Địa chỉ, Số phòng, Trạng thái,..  |
|                    | và lưu thay đổi vào CSDL                        |
|                    |                                                 |
|                    | 3.4. Thông báo "Sửa" thông tin trọ thành công.  |
+--------------------+-------------------------------------------------+
| 3c. Nếu Chủ trọ    | 3.1 Nhận thao tác "Xoá" của chủ trọ.            |
| bấm "Xoá"          |                                                 |
|                    | 3.2. Nhận thông tin của trọ mà chủ trọ muốn     |
|                    | "Xoá" khi chủ trọ bấm vào.                      |
|                    |                                                 |
|                    | 3.3. Tiến hành "Xoá" trọ và lưu thay đổi vào    |
|                    | CSDL                                            |
|                    |                                                 |
|                    | 3.4. Thông báo "Xoá" trọ thành công.            |
+--------------------+-------------------------------------------------+

16. **Kịch bản Use-Case Quản lý Giao Dịch:**

+-----------------+----------------------------------------------------+
| Tên use case    | Quản Lý Giao Dịch                                  |
+=================+====================================================+
| Tên Actor       | Chủ trọ                                            |
+-----------------+----------------------------------------------------+
| Mức             | 1                                                  |
+-----------------+----------------------------------------------------+
| Tiền điều kiện  | Chủ trọ đã đăng nhập; tồn tại ít nhất 1 bản ghi    |
|                 | giao dịch trong hệ thống                           |
+-----------------+----------------------------------------------------+
| Đảm bảo tối     | Giao diện "Quản lý giao dịch" hiển thị bảng danh   |
| thiểu           | sách giao dịch (có thể rỗng)                       |
+-----------------+----------------------------------------------------+
| Đảm bảo thành   | Hiển thị đầy đủ giao dịch và cho phép Chủ trọ thực |
| công            | hiện các thao tác: xác nhận thanh toán, ghi nợ,    |
|                 | sửa, xóa                                           |
+-----------------+----------------------------------------------------+
| Kích hoạt       | Chủ trọ click menu "Quản lý giao dịch"             |
+-----------------+----------------------------------------------------+
| **Hành động tác | **Phản ứng hệ thống**                              |
| nhân**          |                                                    |
+-----------------+----------------------------------------------------+
| 1\. Chủ trọ     | 1.1. Truy vấn CSDL các giao dịch của các phòng     |
| chọn "Quản lý   | thuộc quyền quản lý.                               |
| Giao Dịch"      |                                                    |
|                 | 1.2. Hiển thị bảng với các cột: ID, Phòng, Khách,  |
|                 | Loại, Số tiền, Trạng thái, Ngày,..                 |
+-----------------+----------------------------------------------------+
| 2\. Chủ trọ     | 2.1 Hệ thống chờ nhận thao tác                     |
| nhìn bảng và    |                                                    |
| quyết định thao |                                                    |
| tác             |                                                    |
+-----------------+----------------------------------------------------+
| 3a. Nếu bấm     | 3.1 Nhận thao tác "Xác nhận thanh toán" của chủ    |
| "Xác nhận thanh | trọ.                                               |
| toán" trên một  |                                                    |
| giao dịch đang  | 3.2. Hiển thị modal xác nhận.                      |
| chờ             |                                                    |
|                 | 3.3. Khi ấn OK thì cập nhật trạng tháo giao dịch   |
|                 | thành "Đã thanh toán".                             |
+-----------------+----------------------------------------------------+
| 3b. Nếu Chủ trọ | 3.1 Nhận thao tác "Sửa" giao dịch của chủ trọ.     |
| bấm "Sửa"       |                                                    |
|                 | 3.2. Nhận thông tin của giao dịch mà chủ trọ muốn  |
|                 | "Sửa" khi chủ trọ bấm vào.                         |
|                 |                                                    |
|                 | 3.3. Tiến hành "Sửa" thông tin của trọ như oại, Số |
|                 | tiền, Ngày,.. và lưu thay đổi vào CSDL             |
|                 |                                                    |
|                 | 3.4. Thông báo "Sửa" thông tin giao dịch thành     |
|                 | công.                                              |
+-----------------+----------------------------------------------------+
| 3c. Nếu Chủ trọ | 3.1 Nhận thao tác "Xoá" giao dịch của chủ trọ.     |
| bấm "Xoá"       |                                                    |
|                 | 3.2. Nhận thông tin của giao dịch mà chủ trọ muốn  |
|                 | "Xoá" khi chủ trọ bấm vào.                         |
|                 |                                                    |
|                 | 3.3. Tiến hành "Xoá" giao dịch đó và lưu thay đổi  |
|                 | vào CSDL                                           |
|                 |                                                    |
|                 | 3.4. Thông báo "Xoá" giao dịch thành công.         |
+-----------------+----------------------------------------------------+

**\
**

17. **Kịch bản Use-Case Quản Lý Hợp Đồng:**

+-----------------+----------------------------------------------------+
| Tên use case    | Quản Lý Hợp Đồng                                   |
+=================+====================================================+
| Tên Actor       | Chủ trọ                                            |
+-----------------+----------------------------------------------------+
| Mức             | 1                                                  |
+-----------------+----------------------------------------------------+
| Tiền điều kiện  | Chủ trọ đã đăng nhập; tồn tại ít nhất 1 bản ghi    |
|                 | giao dịch trong hệ thống                           |
+-----------------+----------------------------------------------------+
| Đảm bảo tối     | Giao diện "Quản lý giao dịch" hiển thị bảng danh   |
| thiểu           | sách giao dịch (có thể rỗng)                       |
+-----------------+----------------------------------------------------+
| Đảm bảo thành   | Hiển thị đầy đủ giao dịch và cho phép Chủ trọ thực |
| công            | hiện các thao tác: xác nhận thanh toán, ghi nợ,    |
|                 | sửa, xóa                                           |
+-----------------+----------------------------------------------------+
| Kích hoạt       | Chủ trọ click menu "Quản lý giao dịch"             |
+-----------------+----------------------------------------------------+
| **Hành động tác | **Phản ứng hệ thống**                              |
| nhân**          |                                                    |
+-----------------+----------------------------------------------------+
| 1\. Chủ trọ     | 1.1. Truy vấn CSDL các giao dịch của các phòng     |
| chọn "Quản lý   | thuộc quyền quản lý.                               |
| Giao Dịch"      |                                                    |
|                 | 1.2. Hiển thị bảng với các cột: ID, Phòng, Khách,  |
|                 | Loại, Số tiền, Trạng thái, Ngày,..                 |
+-----------------+----------------------------------------------------+
| 2\. Chủ trọ     | 2.1 Hệ thống chờ nhận thao tác                     |
| nhìn bảng và    |                                                    |
| quyết định thao |                                                    |
| tác             |                                                    |
+-----------------+----------------------------------------------------+
| 3a. Nếu bấm     | 3.1 Nhận thao tác "Xác nhận thanh toán" của chủ    |
| "Xác nhận thanh | trọ.                                               |
| toán" trên một  |                                                    |
| giao dịch đang  | 3.2. Hiển thị modal xác nhận.                      |
| chờ             |                                                    |
|                 | 3.3. Khi ấn OK thì cập nhật trạng tháo giao dịch   |
|                 | thành "Đã thanh toán".                             |
+-----------------+----------------------------------------------------+
| 3b. Nếu Chủ trọ | 3.1 Nhận thao tác "Sửa" giao dịch của chủ trọ.     |
| bấm "Sửa"       |                                                    |
|                 | 3.2. Nhận thông tin của giao dịch mà chủ trọ muốn  |
|                 | "Sửa" khi chủ trọ bấm vào.                         |
|                 |                                                    |
|                 | 3.3. Tiến hành "Sửa" thông tin của trọ như oại, Số |
|                 | tiền, Ngày,.. và lưu thay đổi vào CSDL             |
|                 |                                                    |
|                 | 3.4. Thông báo "Sửa" thông tin giao dịch thành     |
|                 | công.                                              |
+-----------------+----------------------------------------------------+
| 3c. Nếu Chủ trọ | 3.1 Nhận thao tác "Xoá" giao dịch của chủ trọ.     |
| bấm "Xoá"       |                                                    |
|                 | 3.2. Nhận thông tin của giao dịch mà chủ trọ muốn  |
|                 | "Xoá" khi chủ trọ bấm vào.                         |
|                 |                                                    |
|                 | 3.3. Tiến hành "Xoá" giao dịch đó và lưu thay đổi  |
|                 | vào CSDL                                           |
|                 |                                                    |
|                 | 3.4. Thông báo "Xoá" giao dịch thành công.         |
+-----------------+----------------------------------------------------+

18. **Kịch bản Use-Case Quản lý thông báo**

+-----------------+----------------------------------------------------+
| Tên use case    | Quản Lý thông báo                                  |
+=================+====================================================+
| Tên Actor       | Chủ trọ                                            |
+-----------------+----------------------------------------------------+
| Mức             | 1                                                  |
+-----------------+----------------------------------------------------+
| Tiền điều kiện  | Chủ trọ đã đăng nhập hệ thống thành công           |
+-----------------+----------------------------------------------------+
| Đảm bảo tối     | Hiển thị được danh sách thông báo đã gửi/nhận (có  |
| thiểu           | thể rỗng)                                          |
+-----------------+----------------------------------------------------+
| Đảm bảo thành   | Cho phép chủ trọ xem danh sách, phản hồi, xóa hoặc |
| công            | tạo mới thông báo                                  |
+-----------------+----------------------------------------------------+
| Kích hoạt       | Chủ trọ click menu "Quản lý thông báo"             |
+-----------------+----------------------------------------------------+
| **Hành động tác | **Phản ứng hệ thống**                              |
| nhân**          |                                                    |
+-----------------+----------------------------------------------------+
| 1\. Chọn chức   | 1.1. Hệ thống lấy danh sách thông báo liên quan    |
| năng "Quản lý   | đến chủ trọ từ CSDL.\                              |
| thông báo"      | 1.2. Hiển thị bảng: tiêu đề, người gửi, ngày gửi,  |
|                 | trạng thái.                                        |
|                 |                                                    |
|                 | 1.3. Hiển thị bảng phân trang các thông báo.       |
+-----------------+----------------------------------------------------+
| 2.Chủ trọ chọn  | 2.1 Màn hình sẽ hiện ra nút "Gửi tin nhắn" và "Xoá |
| chức năng "Gửi  | Thông Báo" trên từng thông báo                     |
| Tin Nhắn"       |                                                    |
+-----------------+----------------------------------------------------+
| 3\. Chủ trọ     | 3.1 Hệ thống nhận được yêu cầu từ chủ trọ.         |
| chọn "Gửi Tin   |                                                    |
| Nhắn"           | 3.2 Hiển thị form điều gồm nhiều trường như Tiêu   |
|                 | đề thông báo, Nội dung,... nút Gửi, Huỷ            |
+-----------------+----------------------------------------------------+
| 4\. Chủ trọ     | 4.1 Hệ thống sẽ kiểm tra lại xem đã điền đầy đủ    |
| chọn "Gửi"      | thông tin chưa?                                    |
|                 |                                                    |
|                 | 4.2 Nếu điều đầy đủ rồi thì sẽ tiến hành Gửi thông |
|                 | báo                                                |
|                 |                                                    |
|                 | 4.3 Nếu chưa thì sẽ yêu cầu điền đầy đủ lại        |
+-----------------+----------------------------------------------------+
| 5.Chủ trọ chọn  | 5.1 Hệ thống sẽ xác định muốn xoá thông báo nào?   |
| "Xoá thông báo" |                                                    |
|                 | 5.2 Hiển thị thông báo xác nhận muốn xoá           |
+-----------------+----------------------------------------------------+
| 6.Chủ trọ ấn    | 6.1 Hệ thống nhận được yêu cầu "Xoá thông báo"     |
| "Xoá"           |                                                    |
|                 | 6.2 Tiến hành xoá thông báo                        |
+-----------------+----------------------------------------------------+

19. **Kịch bản Use-Case Duyệt yêu cầu thuê**

  -----------------------------------------------------------------------
  Tên use case       Duyệt yêu cầu thuê
  ------------------ ----------------------------------------------------
  Tên Actor          Chủ trọ

  Mức                1

  Tiền điều kiện     Chủ trọ đã đăng nhập; tồn tại 1 hoặc nhiều "Yêu cầu
                     thuê" đang chờ duyệt

  Đảm bảo tối thiểu  Giao diện hiện danh sách yêu cầu thuê (có thể rỗng)

  Đảm bảo thành công Yêu cầu được chuyển sang trạng thái "Đã duyệt" hoặc
                     "Từ chối"; nếu duyệt thì khởi tạo được hợp đồng

  Kích hoạt          Chủ trọ click menu "Yêu cầu thuê"

  **Hành động tác    **Phản ứng hệ thống**
  nhân**             

  1\. Chủ trọ vào    1.1. Truy vấn CSDL các yêu cầu có trạng thái "Chờ
  trang "Yêu cầu     duyệt".\
  thuê".             1.2. Hiển thị bảng danh sách với các cột: Mã, Khách,
                     Phòng, Ngày gửi, Ghi chú ngắn,\...

  2\. . Chủ trọ chọn 2.1 Hiển thị toàn bộ thông tin yêu cầu
  1 dòng yêu cầu và  
  nhấn nút "Xem chi  
  tiết"              

  3\. Trên màn hình  3.1. Hệ thống hiển thị form khởi tạo hợp đồng thuê\
  chi tiết, Chủ trọ  3.2. Chủ trọ điền bổ sung thông tin cần thiết (Giá
  nhấn "Phê duyệt"   thuê, Điều khoản) → nhấn "Lưu hợp đồng".

  4\. Hệ thống lưu   4.1. Cập nhật trạng thái Yêu cầu = "Đã duyệt".\
  hợp đồng và trả về 4.2. Tự động gửi thông báo kết quả phê duyệt tới
  kết quả            khách.\
                     4.3. Hiển thị "Duyệt thành công".
  -----------------------------------------------------------------------

**\
**

20. **Kịch bản Use-Case Quản Lý Thanh Toán**

+-----------------+----------------------------------------------------+
| Tên use case    | Quản Lý Thanh Toán                                 |
+=================+====================================================+
| Tên Actor       | Chủ trọ                                            |
+-----------------+----------------------------------------------------+
| Mức             | 1                                                  |
+-----------------+----------------------------------------------------+
| Tiền điều kiện  | Chủ trọ đã đăng nhập; tồn tại ít nhất 1 giao dịch  |
|                 | thanh toán hoặc ghi nợ trong hệ thống              |
+-----------------+----------------------------------------------------+
| Đảm bảo tối     | Hiển thị danh sách các bản ghi thanh toán (có thể  |
| thiểu           | rỗng)                                              |
+-----------------+----------------------------------------------------+
| Đảm bảo thành   | Cho phép chủ trọ xác nhận, ghi nợ hoặc sửa thông   |
| công            | tin một giao dịch thành công                       |
+-----------------+----------------------------------------------------+
| Kích hoạt       | Chủ trọ click menu "Quản lý thanh toán"            |
+-----------------+----------------------------------------------------+
| **Hành động tác | **Phản ứng hệ thống**                              |
| nhân**          |                                                    |
+-----------------+----------------------------------------------------+
| 1\. Chủ trọ     | 1.1. Truy vấn CSDL lấy danh sách giao dịch (đã     |
| chọn "Quản lý   | thanh toán, chờ xác nhận, ghi nợ).\                |
| thanh toán".    | 1.2. Hiển thị bảng: Mã GD, Phòng, Khách, Loại, Số  |
|                 | tiền, Trạng thái, Ngày.                            |
+-----------------+----------------------------------------------------+
| 2\. Chủ trọ xem | 2.1 Hiển thị các nút Xác nhận, Ghi nợ hoặc Sửa.    |
| bảng và chọn 1  |                                                    |
| giao dịch để    |                                                    |
| thao tác.       |                                                    |
+-----------------+----------------------------------------------------+
| 3a. Nếu Chủ trọ | 3a.1. Hệ thống hiển thị form xác nhận\             |
| bấm "Xác nhận   | 3a.2. Thay đổi trạng thái giao dịch từ "Chờ xác    |
| thanh toán"     | nhận" -\> "Đã thanh toán"                          |
| trên giao dịch  |                                                    |
| chờ xác nhận    |                                                    |
+-----------------+----------------------------------------------------+
| 3b. Nếu Chủ trọ | 3b.1. Hiển thị form ghi số tiền và ngày trả\       |
| bấm "Ghi nợ"    | 3b.2. Tạo bảng ghi nợ\                             |
| trên giao dịch  | 3b.3. Hiển thị "Ghi nợ thành công" và chuyển trạng |
| chưa trả        | thái từ "Chờ Xác Nhận" -\> "Nợ".                   |
+-----------------+----------------------------------------------------+
| 3c. Nếu Chủ trọ | 3c.1 Hiển thị dữ liệu cũ                           |
| bấm "Sửa" trên  |                                                    |
| một dòng giao   | 3c.2 Cho phép cập nhật dữ liệu mới                 |
| dịch            |                                                    |
|                 | 3c.3 Lưu thông tin đã chỉnh sửa vào CSDL           |
|                 |                                                    |
|                 | 3c.4 Thông báo "Chỉnh sửa thành công"              |
+-----------------+----------------------------------------------------+

**\
**

21. **Kịch bản cho Use-Case Thống Kê Hệ thống**

  -----------------------------------------------------------------------
  Tên use case       Thống Kê Hệ Thống
  ------------------ ----------------------------------------------------
  Tên Actor          Chủ trọ

  Mức                1

  Tiền điều kiện     Chủ trọ đã đăng nhập; có ít nhất một giao dịch
                     (thanh toán hoặc ghi nợ) trong hệ thống

  Đảm bảo tối thiểu  Giao diện thống kê tải lên (dù dữ liệu có thể rỗng)

  Đảm bảo thành công Hiển thị đầy đủ các báo cáo: tổng doanh thu, tổng
                     công nợ, biểu đồ phân tích theo thời gian hoặc theo
                     phòng

  Kích hoạt          Chủ trọ click menu "Thống kê hệ thống"

  **Hành động tác    **Phản ứng hệ thống**
  nhân**             

  1\. Chủ trọ chọn   1.1. Hệ thống hiển thị 2 nút Doanh Thu và Công nợ
  "Thống kê hệ       
  thống"             

  2\. Hệ thống thu   2.1 Tính tổng doanh thu trong kỳ (ví dụ:
  thập dữ liệu       tháng/năm).\
                     2.2 Tính tổng công nợ hiện tại.

  3\. Hệ thống hiển  3.1. Hệ thống hiển thị form xác nhận\
  thị báo cáo        3.2. Thay đổi trạng thái giao dịch từ "Chờ xác nhận"
                     -\> "Đã thanh toán"
  -----------------------------------------------------------------------

**\
**

22. **Kịch bản Use-Case Quản lý Người Dùng:**

  -----------------------------------------------------------------------
  Tên use case       Quản Lý Người Dùng
  ------------------ ----------------------------------------------------
  Tên Actor          Admin

  Mức                1

  Tiền điều kiện     Admin đã đăng nhập thành công; trong hệ thống có tối
                     thiểu một tài khoản người dùng

  Đảm bảo tối thiểu  Giao diện "Quản lý người dùng" tải lên

  Đảm bảo thành công Hiển thị danh sách user và cho phép thêm/sửa/xóa
                     thành công

  Kích hoạt          Admin click menu "Quản lý người dùng"

  **Hành động tác    **Phản ứng hệ thống**
  nhân**             

  1\. Admin chọn     1.1. Hệ thống truy vấn CSDL và hiển thị bảng danh
  "Quản lý người     sách người dùng với các cột: ID, Họ tên, Email, Vai
  dùng"              trò, Trạng thái.

  2\. Admin xem bảng 2.1 Hệ thống hiển thị danh sách user, cho phép sắp
                     xếp và tìm kiếm nhanh

  3\. Admin click    3.1. Hệ thống mở form "Thêm người dùng" với các
  "Thêm"             trường: Họ tên, Email, Mật khẩu, Chọn vai trò.\
                     3.2. Admin nhập dữ liệu và nhấn "Lưu".\
                     3.3. Hệ thống kiểm tra hợp lệ; nếu OK: tạo user,
                     thông báo "Thêm thành công"

  4\. Admin chọn 1   4.1. Hệ thống mở form dữ liệu hiện tại.\
  dòng rồi click     4.2. Admin chỉnh sửa (Họ tên, Email, Vai trò) và
  "Sửa"              nhấn "Lưu".\
                     4.3. Hệ thống kiểm tra và cập nhật CSDL; thông báo
                     "Cập nhật thành công"

  5\. Admin chọn     5.1. Hệ thống hiển thị hộp thoại xác nhận "Bạn có
  dòng rồi click     chắc muốn xóa người dùng đã chọn?".\
  "Xóa"              5.2. Nếu Admin xác nhận: xóa bản ghi khỏi CSDL,
                     thông báo "Xóa thành công".
  -----------------------------------------------------------------------

**\
**

23. **Kịch bản Use-Case Phân Quyền Người Dùng**

+-----------------+----------------------------------------------------+
| Tên use case    | Phân Quyền Người Dùng                              |
+=================+====================================================+
| Tên Actor       | Admin                                              |
+-----------------+----------------------------------------------------+
| Mức             | 2                                                  |
+-----------------+----------------------------------------------------+
| Tiền điều kiện  | \- Admin đã đăng nhập thành công                   |
|                 |                                                    |
|                 | \- Admin đang ở màn "Quản lý người dùng" và đã     |
|                 | chọn 1 user                                        |
+-----------------+----------------------------------------------------+
| Đảm bảo tối     | Hiển thị form "Phân quyền" với danh sách quyền và  |
| thiểu           | trạng thái checkbox để chọn quyền                  |
+-----------------+----------------------------------------------------+
| Đảm bảo thành   | Các quyền mới được lưu, user có đúng tập quyền,    |
| công            | thông báo "Cập nhật phân quyền thành công"         |
+-----------------+----------------------------------------------------+
| Kích hoạt       | Admin click nút "Phân quyền" trên dòng user đã     |
|                 | chọn                                               |
+-----------------+----------------------------------------------------+
| **Hành động tác | **Phản ứng hệ thống**                              |
| nhân**          |                                                    |
+-----------------+----------------------------------------------------+
| 1\. Admin click | 1.1. Hệ thống load danh sách Tất cả quyền từ       |
| "Phân quyền"    | CSDL.\                                             |
| cho một user    | 1.2. Đánh dấu checkbox các quyền user đang có.     |
+-----------------+----------------------------------------------------+
| 2\. Admin       | 2.1. Hệ thống hiển thị ngay thay đổi checkbox      |
| tick/untick các |                                                    |
| quyền cần gán   |                                                    |
| hoặc thu hồi    |                                                    |
+-----------------+----------------------------------------------------+
| 3\. Admin nhấn  | 3.1. Cập nhật CSDL.                                |
| "Lưu"           |                                                    |
|                 | 3.2 Hiển thị cập nhật quyền thành công             |
|                 |                                                    |
|                 | 3.3 Quay về màn "Quản lý người dùng" và reload     |
|                 | danh sách người dùng.                              |
+-----------------+----------------------------------------------------+
