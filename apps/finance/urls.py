from django.urls import path
from . import views

urlpatterns = [

    # ===========================
    # Financial Dashboard
    # ===========================
    path(
        "",
        views.financial_dashboard,
        name="financial_dashboard"
    ),

    # ===========================
    # Journal & Voucher History
    # ===========================
    path(
        "journals/",
        views.journal_list,
        name="journal_list"
    ),

    path(
        "journal/<str:journal_id>/",
        views.journal_detail,
        name="journal_detail"
    ),

    # ===========================
    # Receive Payment (Both Direct & Journal-wise)
    # ===========================
    path(
        "receive-payment/",
        views.receive_payment,
        name="receive_payment"
    ),

    path(
        "journal/<str:journal_id>/receive/",
        views.receive_payment,
        name="receive_payment_journal"
    ),

    path(
        "receive-payment/account/<int:account_id>/",
        views.receive_payment,
        name="receive_payment_account"
    ),

    # ===========================
    # Make Payment (Both Direct & Journal-wise)
    # ===========================
    path(
        "make-payment/",
        views.make_payment_view,
        name="make_payment"
    ),

    path(
        "journal/<str:journal_id>/make-payment/",
        views.make_payment_view,
        name="make_payment_journal"
    ),

    path(
        "make-payment/account/<int:account_id>/",
        views.make_payment_view,
        name="make_payment_account"
    ),

    # ===========================
    # Contra Voucher (Cash/Bank Transfer)
    # ===========================
    path(
        "contra/create/",
        views.create_contra,
        name="create_contra"
    ),

    # ===========================
    # Manual Voucher CRUD
    # ===========================
    path(
        "vouchers/",
        views.voucher_list,
        name="voucher_list"
    ),

    path(
        "voucher/create/",
        views.voucher_create,
        name="voucher_create"
    ),

    path(
        "voucher/<str:voucher_no>/",
        views.voucher_detail,
        name="voucher_detail"
    ),

    path(
        "voucher/<str:voucher_no>/edit/",
        views.voucher_edit,
        name="voucher_edit"
    ),

    path(
        "voucher/<str:voucher_no>/post/",
        views.voucher_post,
        name="voucher_post"
    ),

    path(
        "voucher/<str:voucher_no>/cancel/",
        views.voucher_cancel,
        name="voucher_cancel"
    ),

    path(
        "voucher/<str:voucher_no>/delete/",
        views.voucher_delete,
        name="voucher_delete"
    ),

    path(
        "voucher/<str:voucher_no>/pdf/",
        views.voucher_pdf,
        name="voucher_pdf"
    ),

    path(
        "voucher/<str:voucher_no>/print/",
        views.voucher_print,
        name="voucher_print"
    ),

    # ===========================
    # Chart of Accounts (Account Management)
    # ===========================
    path(
        "accounts/",
        views.account_list,
        name="account_list"
    ),

    path(
        "accounts/create/",
        views.account_create,
        name="account_create"
    ),

    path(
        "accounts/<int:pk>/edit/",
        views.account_update,
        name="account_update"
    ),

    path(
        "accounts/<int:pk>/delete/",
        views.account_delete,
        name="account_delete"
    ),

    path(
        "account/<int:pk>/view/",
        views.account_view,
        name="account_view"
    ),

    # ===========================
    # All Ledgers
    # ===========================
    path(
        "ledger/<int:account_id>/",
        views.ledger_detail,
        name="ledger_detail"
    ),

    path(
        "customers/",
        views.customer_ledger,
        name="customer_ledger"
    ),

    path(
        "products/",
        views.product_ledger,
        name="product_ledger"
    ),

    path(
        "cash/",
        views.cash_ledger,
        name="cash_ledger"
    ),

    path(
        "banks/",
        views.bank_ledger,
        name="bank_ledger"
    ),

    path(
        "assets/",
        views.asset_ledger,
        name="asset_ledger"
    ),

    path(
        "liabilities/",
        views.liability_ledger,
        name="liability_ledger"
    ),

    path(
        "equities/",
        views.equity_ledger,
        name="equity_ledger"
    ),

    path(
        "incomes/",
        views.income_ledger,
        name="income_ledger"
    ),

    path(
        "expenses/",
        views.expense_ledger,
        name="expense_ledger"
    ),

    path(
        "suppliers/",
        views.supplier_ledger,
        name="supplier_ledger"
    ),

    path(
        "receivables/",
        views.receivable_ledger,
        name="receivable_ledger"
    ),

    path(
        "payables/",
        views.payable_ledger,
        name="payable_ledger"
    ),

    path(
        "others/",
        views.other_ledger,
        name="other_ledger"
    ),

    # ===========================
    # Reports & Helpers
    # ===========================
    path(
        "trial-balance/",
        views.trial_balance,
        name="trial_balance"
    ),
    path(
        "trial-balance/pdf/",
        views.trial_balance_pdf,
        name="trial_balance_pdf"
    ),
    path(
        "trial-balance/excel/",
        views.trial_balance_excel,
        name="trial_balance_excel"
    ),
    path("income-statement/", views.income_statement, name="income_statement"),
    path("balance-sheet/", views.balance_sheet, name="balance_sheet"),

    path(
        "get-account-journals/<int:account_id>/",
        views.get_account_journals,
        name="get_account_journals"
    ),
    path("reports/export-all-ledgers-excel/",
         views.export_all_ledgers_excel,
         name="export_all_ledgers_excel"),

]