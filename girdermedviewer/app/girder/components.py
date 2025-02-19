import asyncio
import logging
import traceback
from time import time
from trame.decorators import TrameApp, change
from trame_server.utils.asynchronous import create_task
from trame.widgets import gwc, client
from trame.widgets.vuetify2 import (
    VCard,
    VCol,
    VColorPicker,
    VContainer,
    VDivider,
    VExpansionPanel,
    VExpansionPanelContent,
    VExpansionPanelHeader,
    VExpansionPanels,
    VList,
    VListItem,
    VRangeSlider,
    VRow,
    VSelect,
    VSlider,
    VSubheader,
    VTextField,
)
from .utils import FileFetcher, CacheMode, format_date
from ..utils import Button
from girder_client import GirderClient

logger = logging.getLogger(__name__)
GIRDER_ID_HINT = 'Please provide an ID.'


class GirderDrawer(VContainer):
    def __init__(self, **kwargs):
        super().__init__(
            classes="girder-drawer fill-height pa-0",
            **kwargs
        )
        self._build_ui()

    def _build_ui(self):
        with self:
            with VRow(
                align_content="start",
                justify="center",
                no_gutters=True,
                classes='py-1'
            ):
                with VCol(cols=12):
                    VTextField(
                            label=('girder_id_label', 'Folder ID / URL'),
                            v_model=("girder_id_input", None),
                            autofocus=True,
                            persistent_hint=True,
                            hint=('girder_id_hint', GIRDER_ID_HINT),
                            dense=True,
                            outlined=True,
                            classes="py-1 px-1",
                            error=('girder_id_error', False),
                            success=('girder_id_success', False),
                            append_icon='mdi-refresh',
                            click_append=self.ctrl.reload_girder_id,
                            )

            with VRow(
                style="height:100%",
                align_content="start",
                justify="center",
                dense=True
            ):
                with VCol(cols=12):
                    GirderFileSelector()

                with VCol(v_if=("selected.length > 0",), cols=12):
                    GirderItemList()


class GirderFileSelector(gwc.GirderFileManager):
    def __init__(self, **kwargs):
        super().__init__(
            v_if=("user",),
            v_model=("selected_in_location",),
            location=("location",),
            update_location=(self.update_location, "[$event]"),
            rowclick=(
                self.toggle_item,
                "[$event]"
            ),
            **kwargs
        )
        self.state.selected_in_location = []
        girder_client = GirderClient(apiUrl=self.state.api_url)
        cache_mode = CacheMode(self.state.cache_mode) if self.state.cache_mode else CacheMode.No
        self.file_fetcher = FileFetcher(
            girder_client,
            self.state.assetstore_dir,
            self.state.temp_dir,
            cache_mode
        )
        # FIXME do not use global variable
        global file_selector
        file_selector = self

        self.state.change("location", "selected")(self.on_location_changed)
        self.state.change("api_url")(self.set_api_url)
        self.state.change("user")(self.set_user)

        self.callback()
        self.ctrl.reload_girder_id = self.reload_girder_id

        self.state.url = ''
        # setup  client side function to catch the input url
        client_triggers = trame.ClientTriggers(
            ref="client_triggers",
            method1="url=window.location.href",
        )
        self.ctrl.call = client_triggers.call
        self.ctrl.on_client_connected.add(self.on_client_connected) # make it automnatic


    def on_client_connected(self, *args, **kwargs):
        """ Check for and load the id in input url.
        """
        self.ctrl.call('method1')
        # url reading in ctrl.call, won't be done at called time
        # use async to launch state change afterward.
        async def _load_url(): 
            while not self.file_downloader.girder_client.token: # wait at login screen
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.1)
            if self.state.url.split('/')[-1] != 'index.html':
                self.state.girder_id_input = self.state.url
            else:
                self.state.girder_id_input = ''
            self.state.flush()
        create_task(_load_url())

    def reload_girder_id(self,):
        """
        """
        self.state.dirty('girder_id_input')

    def callback(self,):
        """
        """
        @self.state.change('girder_id_input')
        def on_girder_id_input_changed(girder_id_input, **kwargs):
            """ Find compatible folder ID from the VTextField box.
            """
            if girder_id_input in [None, '']:
                # reset success state
                self.state.girder_id_hint = GIRDER_ID_HINT
                self.state.girder_id_error = False 
                self.state.girder_id_success = False

            else:
                # make it works with whole url
                if '/' in girder_id_input:
                    girder_id_input = girder_id_input.split('/')[-1]
                self.state.girder_id_input = girder_id_input

                try: 
                    ## try loading id as folder
                    location = self.file_downloader.girder_client.getFolder(girder_id_input)
                    self.update_location(location)

                    # change location success
                    self.state.girder_id_error = False
                    self.state.girder_id_success = True
                    self.state.girder_id_hint = "Click ⟳ to reload ID."

                except:
                    # try loading id as item, then get parent folder 
                    try:
                        item = self.file_downloader.girder_client.getItem(girder_id_input)
                        folder_id = item['folderId']
                        location = self.file_downloader.girder_client.getFolder(folder_id)
                        self.update_location(location)

                        # change location success
                        self.state.girder_id_error = False
                        self.state.girder_id_success = True
                        self.state.girder_id_hint = "Click ⟳ to reload ID."

                        ## Auto select files
                        # # self.state.flush()
                        # async def select_item():
                        #     await asyncio.sleep(1)
                        #     self.select_item(item)
                        #     self.state.flush()
                        # # self.select_item(item)
                        # create_task(select_item())

                    except:
                        self.state.girder_id_error = True
                        self.state.girder_id_success = False
                        self.state.girder_id_hint = "Error loading ID, click ⟳ to retry."


    def toggle_item(self, item):
        if item.get('_modelType') != 'item':
            return
        # Ignore double click on item
        clicked_time = time()
        if clicked_time - self.state.last_clicked < 1:
            return
        self.state.last_clicked = clicked_time
        is_selected = item["_id"] in [i["_id"] for i in self.state.selected]
        logger.debug(f"Toggle item {item} selected={is_selected}")
        if is_selected:
            self.unselect_item(item)
        else:
            self.select_item(item)

    def update_location(self, new_location):
        """
        Called each time the user browse through the GirderFileManager.
        """
        logger.debug(f"Updating location to {new_location}")
        self.state.location = new_location

    def unselect_item(self, item):
        self.state.selected = [i for i in self.state.selected if i["_id"] != item["_id"]]
        self.ctrl.remove_data(item["_id"])

    def unselect_items(self):
        while len(self.state.selected) > 0:
            self.unselect_item(self.state.selected[0])

    def select_item(self, item):
        assert item.get('_modelType') == 'item', "Only item can be selected"
        item["humanCreated"] = format_date(item["created"], self.state.date_format)
        item["humanUpdated"] = format_date(item["updated"], self.state.date_format)
        item["parentMeta"] = self.file_fetcher.get_item_inherited_metadata(item)
        item["loading"] = False
        item["loaded"] = False

        self.state.selected = self.state.selected + [item]

        self.create_load_task(item)

    def create_load_task(self, item):
        logger.debug(f"Creating load task for {item}")
        item["loading"] = True
        self.state.dirty("selected")
        self.state.flush()

        async def load():
            await asyncio.sleep(1)
            try:
                self.load_item(item)
                item["loaded"] = True
            finally:
                item["loading"] = False
                self.state.dirty("selected")
                self.state.flush()

        create_task(load())

    def load_item(self, item):
        logger.debug(f"Loading item {item}")
        try:
            files = list(self.file_fetcher.get_item_files(item))
            logger.debug(f"Files to load: {files}")
            if len(files) != 1:
                raise Exception(
                    "No file to load. Please check the selected item."
                    if (not files) else
                    "You are trying to load more than one file. \
                    If so, please load a compressed archive."
                )
            with self.file_fetcher.fetch_file(files[0]) as file_path:
                self.ctrl.load_file(file_path, item["_id"])
        except Exception:
            logger.error(f"Error loading file {item['_id']}: {traceback.format_exc()}")
            self.unselect_item(item)

    def set_api_url(self, api_url, **kwargs):
        logger.debug(f"Setting api_url to {api_url}")
        self.file_fetcher.girder_client = GirderClient(apiUrl=api_url)

    def set_token(self, token):
        self.file_fetcher.girder_client.setToken(token)

    def on_location_changed(self, **kwargs):
        logger.debug(f"Location/Selected changed to {self.state.location}/{self.state.selected}")
        location_id = self.state.location.get("_id", "") if self.state.location else ""
        self.state.selected_in_location = [item for item in self.state.selected
                                           if item["folderId"] == location_id]

    def set_user(self, user, **kwargs):
        logger.debug(f"Setting user to {user}")
        if user:
            self.state.location = self.state.default_location or user
            self.set_token(self.state.token)
        else:
            self.unselect_items()
            self.state.location = None
            self.set_token(None)


@TrameApp()
class GirderItemList(VCard):
    def __init__(self, **kwargs):
        super().__init__(
            **kwargs
        )
        client.Style(".v-expansion-panel-content__wrap { padding: 0 !important; };"
                     ".list-item {}")
        self._build_ui()

    def _build_ui(self):
        with self:
            with VExpansionPanels(accordion=True, focusable=True, multiple=True):
                with client.Getter(
                    v_for="(item, i) in selected",
                    key="item._id",
                    name=("`${item._id}`",),
                    key_name="data_id",
                    value_name="object",
                    update_nested_name="update_object",
                ):
                    GirderItemCard(
                        item="item",
                        key_name="object",
                        value_name="object",
                        update_name="update_object")
            with VCol(cols="auto"):
                Button(
                    tooltip="Clear all",
                    icon="mdi-delete",
                    click=self.clear_views,
                )

    @change("selected")
    def on_new_selection(self, **kwargs):
        # Vue2 only: GirderClient must be re-created for v_for to be refreshed
        self.clear()
        self._build_ui()

    def clear_views(self):
        self.ctrl.clear()
        self.state.selected = []


class GirderItemCard(VExpansionPanel):
    def __init__(self, item, key_name, value_name, update_name, **kwargs):
        super().__init__(**kwargs)
        self.item = item
        self.key_name = key_name
        self.value_name = value_name
        self.update_name = update_name
        self._build_ui()

    def _build_ui(self):
        with self:
            with VExpansionPanelHeader(hide_actions=(f"!{self.item}.loaded",)):
                with VRow(align="center", justify="space-between", dense=True):
                    VCol("{{ " + self.item + ".name }}")
                    with VCol(classes="d-flex justify-end",):
                        Button(
                            tooltip="Delete item",
                            icon="mdi-delete",
                            loading=(f"{self.item}.loading",),
                            disabled=(f"{self.item}.loading",),
                            click_native_stop=(self.delete_item, f"[{self.item}._id]"),
                            __events=[("click_native_stop", "click.native.stop")]
                        )

            with VExpansionPanelContent(v_if=(f"{self.item}.loaded",)):
                ItemSettings(
                    item=self.item,
                    key_name=self.key_name,
                    value_name=self.value_name,
                    update_name=self.update_name
                )
                ItemInfo(item=self.item)
                ItemMetadata(item=self.item)

    def delete_item(self, item_id):
        # redundant with GirdeFileSelector unselect_item
        self.state.selected = [i for i in self.state.selected if i["_id"] != item_id]
        self.ctrl.remove_data(item_id)


class ItemSettings(VCard):
    def __init__(self, item, key_name, value_name, update_name, **kwargs):
        super().__init__(**kwargs)
        self.item = item
        self.key_name = key_name
        self.value_name = value_name
        self.update_name = update_name
        self._build_ui()

    def get(self, prop, condition=""):
        return (self.value_name + '.' + prop + condition,)

    def set(self, prop):
        return self.update_name + "('" + prop + "', $event)"

    def _build_ui(self):
        with self:
            with VList(dense=True, classes="pa-0"):
                with VRow(no_gutters=True,
                          v_if=self.get("opacity", "!= -1")):
                    with VCol(cols=10):
                        with VListItem():
                            VSlider(
                                label='Opacity',
                                value=self.get("opacity"),
                                input=self.set("opacity"),
                                min=0,
                                max=1,
                                step=0.05,
                                thumb_label=True,
                            )
                with VRow(
                    v_if=self.get("preset"),
                    align="center",
                    no_gutters=True
                ):
                    with VCol(cols=12):
                        with VListItem():
                            VSelect(
                                label='Preset',
                                items=("presets",),
                                item_text="name",
                                value=self.get("preset"),
                                change=self.set("preset"),
                            )

                        with VListItem():
                            with VRow(justify="space-between"):
                                with VCol():
                                    VTextField(
                                        value=self.get("preset_min"),
                                        change=self.set("preset_min"),
                                        type="number",
                                        label="Min",
                                        dense=True
                                    )
                                with VCol():
                                    VTextField(
                                        value=self.get("preset_max"),
                                        change=self.set("preset_max"),
                                        type="number",
                                        label="Max",
                                        dense=True,
                                    )

                with VRow(
                    v_if=self.get("window_level_min_max"),
                    align="center",
                    no_gutters=True
                ):
                    with VCol(cols=12):
                        with VListItem():
                            VRangeSlider(
                                label="Window Level",
                                value=self.get("window_level_min_max"),
                                input=self.set("window_level_min_max"),
                                min=self.get("range_min"),
                                max=self.get("range_max"),
                                step=1,
                                thumb_label=True,
                                dense=True
                            )

                with VRow(
                    v_if=self.get("color"),
                    align="center",
                    no_gutters=True
                ):
                    with VCol(cols=2):
                        VSubheader("Color", classes="subtitle-1 font-weight-bold pl-4")
                    with VCol(cols=10):
                        with VListItem():
                            VColorPicker(
                                value=self.get("color"),
                                input=self.set("color"),
                                hide_inputs=True,
                            )


class ItemInfo(VCard):
    def __init__(self, item, **kwargs):
        super().__init__(**kwargs)
        self.item = item
        self._build_ui()

    def _build_ui(self):
        with self:
            VSubheader("Info", classes="subtitle-1 font-weight-bold")
            with VList(dense=True, classes="pa-0", subheader=True):
                VListItem(
                    "Size: {{ " + self.item + ".humanSize}}",
                    classes="py-1 body-2",
                )
                VListItem(
                    "Created on {{ " + self.item + ".humanCreated}}",
                    classes="py-1 body-2",
                )
                VListItem(
                    "Updated on {{ " + self.item + ".humanUpdated}}",
                    classes="py-1 body-2",
                )


class ItemMetadata(VCard):
    def __init__(self, item, **kwargs):
        super().__init__(**kwargs)
        self.item = item
        self._build_ui()

    def _build_ui(self):
        with self:
            VSubheader("Metadata", classes="subtitle-1 font-weight-bold pl-4")
            with VList(dense=True, classes="pa-0", subheader=True):
                with VRow(no_gutters=True), VCol(
                    cols=6,
                    v_for=f"(value, key) in {self.item}.meta"
                ):
                    with VListItem(classes="fill-height py-1 body-2"):
                        with VRow(align="center", justify="space-between", no_gutters=True):
                            VCol(
                                "{{ key }}",
                                classes="shrink font-weight-bold"
                            )
                            VCol(
                                "{{ value }}",
                                classes="d-flex justify-end",
                                style="text-align: right"
                            )

                VDivider(
                    v_if=(f"Object.keys({self.item}.parentMeta).length > 0 && \
                          Object.keys({self.item}.meta).length > 0"))

                with VRow(no_gutters=True), VCol(
                    cols=6,
                    v_for=f"(value, key) in {self.item}.parentMeta",
                ):
                    with VListItem(classes="fill-height py-1 body-2"):
                        with VRow(align="center", justify="space-between", dense=True):
                            VCol(
                                "{{ key }}",
                                classes="shrink font-weight-bold"
                            )
                            VCol(
                                "{{ value }}",
                                classes="d-flex justify-end",
                                style="text-align: right"
                            )
