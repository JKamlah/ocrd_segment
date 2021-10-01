from __future__ import absolute_import

import os.path
from pathlib import Path
import json
from collections import defaultdict

from ocrd_utils import (
    getLogger,
    assert_file_grp_cardinality,
    MIMETYPE_PAGE, MIME_TO_EXT
)
from ocrd_models.ocrd_page import (
    TextRegionType,
    to_xml
)
from ocrd_modelfactory import page_from_file
from ocrd import Processor

from .config import OCRD_TOOL
from .repair import ensure_consistent

TOOL = 'ocrd-segment-replace-lines'

class ReplaceLines(Processor):

    def __init__(self, *args, **kwargs):
        kwargs['ocrd_tool'] = OCRD_TOOL['tools'][TOOL]
        kwargs['version'] = OCRD_TOOL['version']
        super(ReplaceLines, self).__init__(*args, **kwargs)

    def process(self):
        """Replace line information with cropped and edited lines from extract lines.

         The hierarchy will not be changed.

         The most common use case is to change the textEquiv information.
        
        Produce a new output file.
        """
        LOG = getLogger('processor.ReplaceLines')
        assert_file_grp_cardinality(self.input_file_grp, 2, 'original, lines')
        assert_file_grp_cardinality(self.output_file_grp, 1)

        # collect input file
        self.input_file_grp, line_grp = self.input_file_grp.split(',')

        # process input file
        for n, input_file in enumerate(self.input_files):
            page_id = input_file.pageId or input_file.ID
            LOG.info("INPUT FILE %i / %s", n, page_id)
            pcgts = page_from_file(self.workspace.download_file(input_file))
            self.add_metadata(pcgts)
            page = pcgts.get_Page()
            region_line_dict = defaultdict()
            for linefile in self.workspace.mets.find_files(pageId=input_file.url.rsplit('.',1)[0], fileGrp=line_grp):
                gttextfile = Path(linefile.url.replace(MIME_TO_EXT[linefile.mimetype], '.gt.txt'))
                metafile = Path(linefile.url.replace(MIME_TO_EXT[linefile.mimetype], '.json'))
                if not gttextfile.exists(): continue
                with open(gttextfile, 'r') as fin:
                    gttext = fin.read().strip()
                if metafile.exists():
                    with open(metafile, 'r') as fin:
                        metadata = json.loads(fin.read())
                    if metadata.get('text') != gttext:
                        metadata['text'] = gttext
                        region_line_dict[f"{metadata.get('region.ID')}_{metadata.get('line.ID')}"] = metadata
            if not region_line_dict: continue
            for rindex, region in enumerate(page.get_AllRegions()):
                ensure_consistent(region)
                if isinstance(region, TextRegionType):
                    for lindex,line in enumerate(region.get_TextLine()):
                        if region_line_dict.get(region.id + '_' + line.id, None):
                            te = line.get_TextEquiv()[0]
                            te.set_Unicode(region_line_dict.get(region.id + '_' + line.id, None).get('text'))
                            line.set_TextEquiv([te])
                            ensure_consistent(line)

            # update METS (add the PAGE file):
            pcgts.set_Page(page)
            file_id = input_file.url.replace(MIME_TO_EXT[input_file.mimetype], '')
            out = self.workspace.add_file(
                ID=file_id,
                file_grp=self.output_file_grp,
                pageId=input_file.pageId,
                local_filename=os.path.join(self.output_file_grp, file_id + '.xml'),
                mimetype=MIMETYPE_PAGE,
                content=to_xml(pcgts))
            LOG.info('created file ID: %s, file_grp: %s, path: %s',
                     file_id, self.output_file_grp, out.local_filename)