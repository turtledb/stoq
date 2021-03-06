# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2008 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s): Stoq Team <stoq-devel@async.com.br>
##
""" Search dialogs for purchase and related objects """

import datetime
from decimal import Decimal

from stoqlib.domain.views import PurchasedItemAndStockView
from stoqlib.enums import SearchFilterPosition
from stoqlib.gui.editors.purchaseeditor import PurchaseItemEditor
from stoqlib.gui.search.searchcolumns import SearchColumn, Column
from stoqlib.gui.search.searcheditor import SearchEditor
from stoqlib.gui.search.searchoptions import (Any, Today, ThisWeek, NextWeek,
                                              ThisMonth, NextMonth)
from stoqlib.gui.utils.printing import print_report
from stoqlib.lib.translation import stoqlib_gettext
from stoqlib.reporting.purchase import PurchasedItemsReport

_ = stoqlib_gettext


class PurchasedItemsSearch(SearchEditor):
    title = _('Purchased Items Search')
    size = (780, 450)
    search_spec = PurchasedItemAndStockView
    editor_class = PurchaseItemEditor

    def __init__(self, store):
        SearchEditor.__init__(self, store=store)
        self.hide_new_button()

    def _get_date_options(self):
        return [Any, Today, ThisWeek, NextWeek, ThisMonth, NextMonth]

    def on_print_button_clicked(self, button):
        print_report(PurchasedItemsReport, self.results, list(self.results),
                     filters=self.search.get_search_filters())

    #
    # SearchDialog Hooks
    #

    def create_filters(self):
        self.set_text_field_columns(['description'])

        # Branch
        self.branch_filter = self.create_branch_filter(_('In branch:'))
        self.add_filter(self.branch_filter, columns=['branch_id'],
                        position=SearchFilterPosition.TOP)

    #
    # SearchEditor Hooks
    #

    def update_widgets(self):
        selected = self.results.get_selected() is not None
        self.set_edit_button_sensitive(selected)

    def get_columns(self):
        return [SearchColumn('description', title=_('Description'), data_type=str,
                             expand=True, sorted=True),
                SearchColumn('purchased', title=_('Purchased'), data_type=Decimal,
                             width=100),
                SearchColumn('received', title=_('Received'),
                             data_type=Decimal, width=100),
                Column('stocked', title=_('In Stock'), data_type=Decimal,
                       width=100),
                SearchColumn('purchased_date', title=_('Purchased date'),
                             data_type=datetime.date),
                SearchColumn('expected_receival_date', title=_('Expected receival'),
                             data_type=datetime.date,
                             valid_values=self._get_date_options())]

    def get_editor_model(self, model):
        return model.purchase_item
